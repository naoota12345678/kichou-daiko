"""リモートブラウザセッション管理

CDP (Chrome DevTools Protocol) 経由でスクリーンショットを配信し、
ユーザーの入力イベントを中継する。
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from models import Source

# ログイン検出パターン（各サイト）
LOGIN_URLS = {
    "amazon": {
        "login_page": "https://www.amazon.co.jp/gp/your-account/order-history",
        "login_indicators": ["/ap/signin", "/ap/claim"],
    },
    "rakuten": {
        "login_page": "https://order.my.rakuten.co.jp/",
        "login_indicators": ["grp01.id.rakuten.co.jp", "login.account.rakuten.com"],
    },
    "yahoo": {
        "login_page": "https://odhistory.shopping.yahoo.co.jp/order-history/list",
        "login_indicators": ["login.yahoo.co.jp"],
    },
}

# 注文履歴ページ検出JS（各サイト共通パターン）
DETECT_ORDERS_JS = {
    "amazon": r"""() => {
        const body = document.body ? document.body.innerText : '';
        const hasDate = /\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日/.test(body);
        const hasProducts = document.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"]').length > 0;
        const hasOrderId = /\d{3}-\d{7}-\d{7}/.test(body);
        return hasDate || hasProducts || hasOrderId;
    }""",
    "rakuten": r"""() => {
        const body = document.body ? document.body.innerText : '';
        const hasDate = /\d{4}\/\d{1,2}\/\d{1,2}/.test(body);
        const hasOrderLabel = body.includes('注文番号') || body.includes('注文日');
        return hasDate && hasOrderLabel;
    }""",
    "yahoo": r"""() => {
        const body = document.body ? document.body.innerText : '';
        if (body.includes('ログインが必要')) return false;
        if (/\d{4}年\d{1,2}月\d{1,2}日/.test(body)) return true;
        if (body.includes('注文日')) return true;
        return document.querySelectorAll(
            'form[action*="detail"], a[href*="detail"]'
        ).length > 0;
    }""",
}

# スクレイピングJS（各サイト）
SCRAPE_JS = {
    "amazon": r"""() => {
        const results = [];
        let cards = document.querySelectorAll(
            '.order-card, .a-box-group.order, [class*="order-card"]'
        );
        if (cards.length === 0)
            cards = document.querySelectorAll('.order-info, .your-order-card');
        if (cards.length === 0)
            cards = document.querySelectorAll('.a-box-group');

        for (const card of cards) {
            const order = {};
            const cardText = card.textContent || '';
            const dateMatch = cardText.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/);
            if (dateMatch) order.date = dateMatch[0];

            const priceEls = card.querySelectorAll(
                '.a-color-price, [class*="grand-total"], .yohtmlc-order-total'
            );
            for (const el of priceEls) {
                const txt = el.textContent.trim();
                if (/[¥￥]/.test(txt) || /[\d,]+\s*円/.test(txt)) {
                    order.total = txt; break;
                }
            }
            if (!order.total) {
                const pm = cardText.match(/[¥￥]\s*([\d,]+)/);
                if (pm) order.total = pm[0];
            }

            order.products = [];
            const seen = new Set();
            for (const sel of ['.yohtmlc-product-title', 'a[href*="/dp/"]']) {
                for (const el of card.querySelectorAll(sel)) {
                    const name = el.textContent.trim();
                    if (name && name.length > 2 && name.length < 300 && !seen.has(name)) {
                        seen.add(name); order.products.push(name);
                    }
                }
                if (order.products.length > 0) break;
            }

            const idMatch = cardText.match(/\d{3}-\d{7}-\d{7}/);
            if (idMatch) order.orderId = idMatch[0];
            if (order.products.length > 0) results.push(order);
        }
        return results;
    }""",
}


MOBILE_SCRAPE_JS = {
    "amazon": r"""() => {
        const results = [];
        const body = document.body ? document.body.innerText : '';

        // モバイル版: テキストベースでパース
        // 日付パターンで注文ブロックを分割
        const blocks = body.split(/(?=\d{4}年\d{1,2}月\d{1,2}日)/);

        for (const block of blocks) {
            if (!block.trim()) continue;
            const order = {};

            // 日付
            const dateMatch = block.match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
            if (!dateMatch) continue;
            order.date = dateMatch[0];

            // 金額
            const priceMatch = block.match(/[¥￥]\s*([\d,]+)/);
            if (priceMatch) order.total = priceMatch[0];

            // 注文番号
            const idMatch = block.match(/\d{3}-\d{7}-\d{7}/);
            if (idMatch) order.orderId = idMatch[0];

            // 商品名: 行ごとに見て、短すぎず長すぎないものを候補に
            order.products = [];
            const lines = block.split('\n');
            for (const line of lines) {
                const l = line.trim();
                if (l.length >= 5 && l.length < 200 &&
                    !l.match(/^\d{4}年/) &&
                    !l.match(/^[¥￥]/) &&
                    !l.match(/^注文/) &&
                    !l.match(/^配送/) &&
                    !l.match(/^お届け/) &&
                    !l.match(/^返品/) &&
                    !l.match(/^領収書/) &&
                    !l.match(/合計/) &&
                    !l.match(/^再度/) &&
                    !l.match(/^\d+円/) &&
                    !l.match(/^Amazon/) &&
                    l !== '注文の詳細' &&
                    l !== '注文履歴') {
                    order.products.push(l);
                    break; // 最初の商品名だけ
                }
            }

            if (order.products.length > 0 || order.total) {
                if (order.products.length === 0) order.products.push('(商品名不明)');
                results.push(order);
            }
        }

        // DOM版も試す（モバイルでもDOMが使える場合）
        if (results.length === 0) {
            const allLinks = document.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"]');
            const seen = new Set();
            for (const link of allLinks) {
                const name = link.textContent.trim();
                if (name && name.length > 3 && !seen.has(name)) {
                    seen.add(name);
                    results.push({
                        date: '',
                        total: '',
                        orderId: '',
                        products: [name],
                    });
                }
            }
        }

        return results;
    }""",
}


class BrowserSession:
    """1ユーザーの1セッションを管理"""

    def __init__(self, site: str, year: int | None = None):
        self.session_id = str(uuid.uuid4())
        self.site = site
        self.year = year
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.cdp_session: Any = None
        self._pw = None
        self._running = False

    async def start(self):
        """ブラウザを起動してログインページに遷移"""
        print(f"[Browser] Starting for site={self.site}, year={self.year}")
        self._pw = await async_playwright().start()
        print("[Browser] Playwright started")
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.context = await self.browser.new_context(
            locale="ja-JP",
            viewport={"width": 900, "height": 900},
        )
        self.page = await self.context.new_page()
        self.cdp_session = await self.page.context.new_cdp_session(self.page)
        print("[Browser] CDP session created")

        # ログインページに遷移
        login_url = LOGIN_URLS[self.site]["login_page"]
        if self.site == "amazon" and self.year:
            login_url += f"?orderFilter=year-{self.year}"

        try:
            await self.page.goto(login_url, wait_until="networkidle", timeout=30000)
        except Exception:
            await self.page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

        self._running = True
        print(f"[Browser] Ready. URL: {self.page.url[:100]}")

    async def capture_screenshot(self) -> bytes:
        """現在のページのスクリーンショットをJPEGで取得"""
        if not self.cdp_session:
            return b""
        try:
            result = await self.cdp_session.send(
                "Page.captureScreenshot",
                {"format": "jpeg", "quality": 55},
            )
            return base64.b64decode(result["data"])
        except Exception:
            return b""

    async def dispatch_mouse(self, event_type: str, x: int, y: int, button: str = "left"):
        """マウスイベントを送信"""
        if not self.page:
            return
        try:
            if event_type == "click":
                await self.page.mouse.click(x, y, button=button)
            elif event_type == "move":
                await self.page.mouse.move(x, y)
        except Exception:
            pass

    async def focus_input(self):
        """ページ上の最初の可視input/textarea/selectにフォーカス"""
        if not self.page:
            return
        try:
            await self.page.evaluate("""() => {
                const els = document.querySelectorAll('input, textarea, select, [contenteditable="true"]');
                for (const el of els) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && !el.disabled && !el.readOnly) {
                        el.focus();
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
        except Exception:
            pass

    async def dispatch_key(self, key: str, event_type: str = "keyDown"):
        """キーボードイベントを送信"""
        if not self.cdp_session:
            return
        try:
            if key == "Enter":
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "rawKeyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                )
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                )
            elif key == "Tab":
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "rawKeyDown", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
                )
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
                )
            elif key == "Backspace":
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "rawKeyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
                )
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
                )
            else:
                # 通常文字はinsertTextは使わず、dispatch_textで一括送信
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "text": key, "key": key},
                )
                await self.cdp_session.send(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": key},
                )
        except Exception:
            pass

    async def insert_text(self, text: str):
        """テキストを直接挿入（フォーカスされた要素に）"""
        if not self.cdp_session:
            return
        try:
            await self.cdp_session.send(
                "Input.insertText",
                {"text": text},
            )
        except Exception:
            pass

    async def check_login(self) -> bool:
        """ログイン完了を検出"""
        if not self.page:
            return False
        try:
            url = self.page.url
            indicators = LOGIN_URLS[self.site]["login_indicators"]

            # ログインページにいる場合はまだ未ログイン
            if any(ind in url for ind in indicators):
                return False

            # 注文履歴ページの内容を検出
            detect_js = DETECT_ORDERS_JS.get(self.site)
            if detect_js:
                return await self.page.evaluate(detect_js)

            return False
        except Exception:
            return False

    async def scrape(self) -> list[dict]:
        """ログイン後のスクレイピング実行"""
        if not self.page:
            return []

        print(f"[Scrape] Current URL: {self.page.url[:150]}")

        # ログイン後、注文履歴ページに遷移する必要がある場合
        url = self.page.url
        if self.site == "amazon" and "/ap/" in url:
            # まだログインページにいる → 注文履歴に移動
            order_url = "https://www.amazon.co.jp/gp/your-account/order-history"
            if self.year:
                order_url += f"?orderFilter=year-{self.year}"
            print(f"[Scrape] Navigating to order history: {order_url}")
            try:
                await self.page.goto(order_url, wait_until="networkidle", timeout=30000)
            except Exception:
                await self.page.goto(order_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            print(f"[Scrape] Now at: {self.page.url[:150]}")

        items = []

        if self.site == "amazon":
            items = await self._scrape_amazon()
        elif self.site == "rakuten":
            items = await self._scrape_rakuten()
        elif self.site == "yahoo":
            items = await self._scrape_yahoo()

        return items

    async def _scrape_amazon(self) -> list[dict]:
        """Amazonの注文データを抽出"""
        all_items = []
        page_num = 1

        while True:
            await asyncio.sleep(2)
            print(f"[Scrape] Amazon page {page_num}, URL: {self.page.url[:100]}")

            # ページの状態を確認
            body_text = await self.page.evaluate("() => document.body ? document.body.innerText : ''")
            print(f"[Scrape] Body text length: {len(body_text)}")
            print(f"[Scrape] Body preview: {body_text[:500]}")

            # まずデスクトップ用JSを試す
            orders = await self.page.evaluate(SCRAPE_JS["amazon"])
            print(f"[Scrape] Desktop selectors: {len(orders)} order cards")

            # モバイル版フォールバック
            if not orders:
                orders = await self.page.evaluate(MOBILE_SCRAPE_JS["amazon"])
                print(f"[Scrape] Mobile selectors: {len(orders)} order cards")

            for order in orders:
                order_date = self._parse_jp_date(order.get("date", ""))
                if not order_date:
                    continue
                total = self._parse_amount(order.get("total", ""))
                order_id = order.get("orderId", "")
                products = order.get("products", [])
                if not products:
                    continue

                per_item = total / len(products) if total else 0
                for name in products:
                    all_items.append({
                        "orderDate": order_date,
                        "vendor": "Amazon",
                        "productName": name,
                        "amount": int(per_item),
                        "orderId": order_id,
                        "source": "Amazon",
                    })

            # 次のページ
            next_btn = await self.page.query_selector('li.a-last:not(.a-disabled) a')
            if not next_btn:
                break
            await next_btn.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            page_num += 1

        return all_items

    async def _scrape_rakuten(self) -> list[dict]:
        """楽天の注文データを抽出"""
        all_items = []

        # 注文一覧からdetail URLを取得
        summaries = await self.page.evaluate(r"""() => {
            const results = []; const seen = new Set();
            const links = document.querySelectorAll('a[href*="act=detail_page_view"]');
            for (const link of links) {
                const href = link.href || link.getAttribute('href') || '';
                const m = href.match(/order_number=([^&]+)/);
                if (!m) continue;
                const orderId = m[1];
                if (seen.has(orderId)) continue;
                seen.add(orderId);
                let block = link.closest('[class*="spacer"], [class*="block"]') ||
                            link.parentElement.parentElement.parentElement;
                const blockText = block ? block.textContent : '';
                const dm = blockText.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
                results.push({ order_id: orderId, date: dm ? dm[0] : '', detail_url: href });
            }
            return results;
        }""")

        for summary in summaries:
            detail_url = summary.get("detail_url", "")
            if not detail_url:
                continue
            try:
                await self.page.goto(detail_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                data = await self.page.evaluate(r"""() => {
                    try {
                        const state = window.__INITIAL_STATE__;
                        if (!state || !state.orderData) return null;
                        const od = state.orderData;
                        const summary = od.orderSummary || {};
                        const itemObj = od.itemObject || {};
                        return {
                            shop: summary.shopName || '',
                            orderDate: summary.orderCreationDate || '',
                            orderNumber: summary.orderNumber || '',
                            items: (itemObj.itemList || []).map(it => ({
                                name: it.itemName || '', price: it.price || 0, units: it.units || 1,
                            })),
                        };
                    } catch(e) { return null; }
                }""")

                if not data:
                    continue

                order_date = self._parse_date_slash(data.get("orderDate", "") or summary.get("date", ""))
                order_id = data.get("orderNumber", "") or summary.get("order_id", "")
                shop = (data.get("shop") or "").strip() or "楽天"

                for jitem in data.get("items", []):
                    price = jitem.get("price", 0)
                    units = jitem.get("units", 1)
                    all_items.append({
                        "orderDate": order_date,
                        "vendor": shop,
                        "productName": jitem.get("name", "(unknown)"),
                        "amount": int(price * units),
                        "orderId": order_id,
                        "source": "楽天",
                    })
            except Exception:
                continue
            await asyncio.sleep(1)

        return all_items

    async def _scrape_yahoo(self) -> list[dict]:
        """Yahooの注文データを抽出"""
        body = await self.page.evaluate("() => document.body ? document.body.innerText : ''")
        items = []
        blocks = re.split(r'(?=\d{4}年\d{1,2}月\d{1,2}日)', body)

        current_date = None
        current_order_id = ""
        current_store = ""

        for block in blocks:
            if not block.strip():
                continue

            date_match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', block.strip())
            if date_match:
                current_date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

            if not current_date:
                continue

            order_match = re.search(r'注文番号[：:]\s*\n?\s*([\w\-]+)', block)
            if order_match:
                current_order_id = order_match.group(1)
                store_match = re.match(r'([a-zA-Z][\w\-]*?)-(\d+)$', current_order_id)
                if store_match:
                    current_store = store_match.group(1)

            lines = block.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                if any(line.startswith(skip) for skip in [
                    '注文', '再度', 'お問い', 'レビュー', '友だち', 'ブロック',
                    '最大', '領収書', 'すべて見る', '一覧', '定期', 'ふるさと',
                    'カラー:', 'サイズ:', '※', 'ようこそ', '現在', '送料',
                ]):
                    continue
                if re.match(r'^\d{4}年', line):
                    continue

                for j in range(i + 1, min(i + 7, len(lines))):
                    next_line = lines[j].strip()
                    price_match = re.match(r'^([\d,]+)円', next_line)
                    if price_match:
                        items.append({
                            "orderDate": current_date,
                            "vendor": current_store or "Yahoo Shopping",
                            "productName": line,
                            "amount": int(price_match.group(1).replace(',', '')),
                            "orderId": current_order_id,
                            "source": "Yahoo",
                        })
                        break

        return items

    def _parse_jp_date(self, text: str) -> str | None:
        m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        return None

    def _parse_date_slash(self, text: str) -> str | None:
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        return None

    def _parse_amount(self, text: str) -> int:
        cleaned = re.sub(r"[¥￥円,\s]", "", text)
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            return 0

    async def download_receipts(self, items: list[dict]) -> list[dict]:
        """各注文の領収書PDFをダウンロードして返す

        Returns:
            [{"orderId": "...", "filename": "...", "pdf": bytes}, ...]
        """
        if not self.page or not items:
            return []

        # order_idでグループ化
        orders: dict[str, list[dict]] = {}
        for item in items:
            oid = item.get("orderId", "")
            if oid:
                orders.setdefault(oid, []).append(item)

        results = []

        if self.site == "amazon":
            results = await self._download_amazon_receipts(orders)
        elif self.site == "rakuten":
            results = await self._download_rakuten_receipts(orders)

        return results

    async def _download_amazon_receipts(self, orders: dict[str, list[dict]]) -> list[dict]:
        """Amazon注文の領収書PDFをダウンロード"""
        results = []

        for i, (order_id, order_items) in enumerate(orders.items(), 1):
            print(f"[Receipt] [{i}/{len(orders)}] {order_id}")

            try:
                # 方法1: 領収書/購入明細書の印刷ページに直接アクセス
                invoice_url = f"https://www.amazon.co.jp/gp/css/summary/print.html?orderID={order_id}"
                try:
                    await self.page.goto(invoice_url, wait_until="networkidle", timeout=30000)
                except Exception:
                    await self.page.goto(invoice_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # ページに領収書の内容があるか確認
                print(f"[Receipt] URL after navigation: {self.page.url[:150]}")
                body_text = await self.page.evaluate("() => document.body ? document.body.innerText : ''")
                print(f"[Receipt] Page text preview: {body_text[:200]}")
                has_invoice = "領収書" in body_text or "購入明細書" in body_text or "注文合計" in body_text

                if not has_invoice:
                    # 方法2: 注文詳細ページから領収書リンクを探す
                    detail_url = f"https://www.amazon.co.jp/gp/your-account/order-details?orderID={order_id}"
                    await self.page.goto(detail_url, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)

                    receipt_link = await self.page.query_selector(
                        'a[href*="invoice"], a[href*="receipt"], '
                        'a:has-text("領収書"), a:has-text("購入明細書")'
                    )

                    if receipt_link:
                        await receipt_link.click()
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass
                        await asyncio.sleep(2)

                        # 新しいタブで開いた場合
                        pages = self.context.pages
                        if len(pages) > 1:
                            self.page = pages[-1]

                pdf_bytes = await self.page.pdf(format="A4", print_background=True)

                # 新しいタブを閉じて元に戻る
                pages = self.context.pages
                if len(pages) > 1:
                    await pages[-1].close()
                    self.page = pages[0]

                # 1注文 = 1PDF
                first = order_items[0]
                total = sum(it.get("amount", 0) for it in order_items)
                date_str = first.get("orderDate", "").replace("-", "")
                vendor = first.get("vendor", "Amazon")
                filename = f"{date_str}_{vendor}_注文{order_id}_{total}.pdf"

                results.append({
                    "orderId": order_id,
                    "filename": filename,
                    "pdf": pdf_bytes,
                    "orderDate": first.get("orderDate", ""),
                })
                print(f"[Receipt] -> {filename} ({len(pdf_bytes)} bytes)")

            except Exception as e:
                print(f"[Receipt] -> Error: {e}")

            await asyncio.sleep(1)

        return results

    async def _download_rakuten_receipts(self, orders: dict[str, list[dict]]) -> list[dict]:
        """楽天注文の領収書PDFをダウンロード"""
        results = []

        for i, (order_id, order_items) in enumerate(orders.items(), 1):
            print(f"[Receipt] [{i}/{len(orders)}] {order_id}")

            try:
                parts = order_id.split("-")
                shop_id = parts[0] if parts else ""
                detail_url = (
                    f"https://order.my.rakuten.co.jp/purchase-history/"
                    f"?order_number={order_id}&shop_id={shop_id}&act=detail_page_view"
                )
                await self.page.goto(detail_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)

                pdf_bytes = await self.page.pdf(format="A4", print_background=True)

                first = order_items[0]
                total = sum(it.get("amount", 0) for it in order_items)
                date_str = first.get("orderDate", "").replace("-", "")
                vendor = first.get("vendor", "楽天")
                filename = f"{date_str}_{vendor}_注文{order_id}_{total}.pdf"

                results.append({
                    "orderId": order_id,
                    "filename": filename,
                    "pdf": pdf_bytes,
                    "orderDate": first.get("orderDate", ""),
                })
                print(f"[Receipt] -> {filename} ({len(pdf_bytes)} bytes)")

            except Exception as e:
                print(f"[Receipt] -> Error: {e}")

            await asyncio.sleep(1)

        return results

    def _str_to_date(self, date_str: str):
        """YYYY-MM-DD文字列をdateに変換"""
        from datetime import date as date_type
        try:
            parts = date_str.split("-")
            return date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            return date_type.today()

    async def close(self):
        """ブラウザを閉じる"""
        self._running = False
        try:
            if self.browser:
                await self.browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
