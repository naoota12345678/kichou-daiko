"""Amazon注文履歴スクレイパー

Playwrightブラウザでログイン -> ログイン状態を保存 -> 全ページ自動取得。
初回のみログインが必要。2回目以降は保存済みセッションを再利用。
"""

from __future__ import annotations

import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

from models import OrderItem, ParseResult, Source

ORDER_HISTORY_URL = "https://www.amazon.co.jp/gp/your-account/order-history"
STATE_FILE = Path.home() / ".acc-tool" / "amazon_session.json"


def scrape_amazon(
    year: int | None = None,
    save_html_dir: Path | None = None,
    headless: bool = False,
) -> ParseResult:
    """Amazon注文履歴を全ページスクレイピング"""
    all_items: list[OrderItem] = []
    errors: list[str] = []

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # 前回のログイン状態があれば再利用
        if STATE_FILE.exists():
            print("Saved session found. Reusing login state...")
            context = browser.new_context(
                storage_state=str(STATE_FILE),
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )
        else:
            print("No saved session. You will need to log in.")
            context = browser.new_context(
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )

        page = context.new_page()

        # 注文履歴ページへ
        url = ORDER_HISTORY_URL
        if year:
            url += f"?orderFilter=year-{year}"

        page.goto(url, wait_until="networkidle")
        time.sleep(2)

        current_url = page.url
        print(f"  URL: {current_url[:120]}")

        # ログインが必要かチェック
        if "/ap/signin" in current_url or "/ap/claim" in current_url:
            print("")
            print("========================================")
            print("  Browser window is open.")
            print("  Please log in to Amazon.")
            print("  (waiting up to 5 minutes)")
            print("========================================")
            print("")
            _wait_for_order_history(page)

            # ログイン状態を保存
            context.storage_state(path=str(STATE_FILE))
            print("[OK] Login successful. Session saved for next time.")

        print("[OK] Order history page loaded.")

        # 年の選択（指定がある場合）
        if year:
            _select_year(page, year)

        # 全ページ取得
        page_num = 1
        while True:
            print(f"  Page {page_num} ...")

            html = page.content()

            if save_html_dir:
                save_html_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_html_dir / f"amazon_orders_p{page_num}.html"
                save_path.write_text(html, encoding="utf-8")

            page_items = _extract_orders_from_page(page)
            all_items.extend(page_items)
            print(f"    -> {len(page_items)} orders")

            # 次のページ
            next_btn = page.query_selector('li.a-last:not(.a-disabled) a')
            if not next_btn:
                next_btn = page.query_selector('a.s-pagination-next')
            if not next_btn:
                break

            next_btn.click()
            try:
                page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(3)
            page_num += 1

        # セッション更新
        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n[OK] Total: {len(all_items)} orders")

    if not all_items:
        errors.append("No order data extracted. HTML saved for debugging.")

    return ParseResult(items=all_items, errors=errors, source=Source.AMAZON)


def _wait_for_order_history(page: Page, timeout_sec: int = 300) -> None:
    """ユーザーのログイン完了を待つ

    URLではなくページの中身（DOM）で判定する。
    注文履歴ページには商品リンク(/dp/)や注文日の日付が含まれる。
    """
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        try:
            # 注文履歴ページの特徴的な要素を探す
            has_orders = page.evaluate("""() => {
                const body = document.body ? document.body.innerText : '';
                // 注文日パターンがあるか
                const hasDate = /\\d{4}年\\d{1,2}月\\d{1,2}日/.test(body);
                // 商品リンクがあるか
                const hasProducts = document.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"]').length > 0;
                // 注文番号があるか
                const hasOrderId = /\\d{3}-\\d{7}-\\d{7}/.test(body);
                return hasDate || hasProducts || hasOrderId;
            }""")
            if has_orders:
                print("  [OK] Order history detected in page content.")
                time.sleep(2)
                return
        except Exception:
            pass
        time.sleep(1)

    raise TimeoutError("Login timed out.")


def _select_year(page: Page, year: int) -> None:
    """注文履歴の年を選択"""
    try:
        select = page.query_selector('#orderFilter, select[name="orderFilter"], #time-filter')
        if select:
            select.select_option(f"year-{year}")
            page.wait_for_load_state("networkidle")
            time.sleep(1)
    except Exception:
        pass


def _extract_orders_from_page(page: Page) -> list[OrderItem]:
    """1ページ分の注文データをJSで抽出"""
    orders = page.evaluate(r"""() => {
        const results = [];

        // Strategy 1: order-card
        let cards = document.querySelectorAll(
            '.order-card, .a-box-group.order, [class*="order-card"]'
        );
        // Strategy 2: order-info
        if (cards.length === 0)
            cards = document.querySelectorAll('.order-info, .your-order-card');
        // Strategy 3: generic box groups
        if (cards.length === 0)
            cards = document.querySelectorAll('.a-box-group');

        for (const card of cards) {
            const order = {};
            const cardText = card.textContent || '';

            // Date
            const dateMatch = cardText.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/);
            if (dateMatch) {
                order.date = dateMatch[0];
            }

            // Total price
            const priceEls = card.querySelectorAll(
                '.a-color-price, [class*="grand-total"], .yohtmlc-order-total, span.a-color-price'
            );
            for (const el of priceEls) {
                const txt = el.textContent.trim();
                if (/[¥￥]/.test(txt) || /[\d,]+\s*円/.test(txt)) {
                    order.total = txt;
                    break;
                }
            }
            // Fallback: regex from card text
            if (!order.total) {
                const pm = cardText.match(/[¥￥]\s*([\d,]+)/);
                if (pm) order.total = pm[0];
            }

            // Product names
            order.products = [];
            const seen = new Set();
            const productSels = [
                '.yohtmlc-product-title',
                'a[class*="product-title"]',
                'a[href*="/dp/"]',
                'a[href*="/gp/product/"]',
            ];
            for (const sel of productSels) {
                for (const el of card.querySelectorAll(sel)) {
                    const name = el.textContent.trim();
                    if (name && name.length > 2 && name.length < 300 && !seen.has(name)) {
                        seen.add(name);
                        order.products.push(name);
                    }
                }
                if (order.products.length > 0) break;
            }

            // Order ID
            const idMatch = cardText.match(/\d{3}-\d{7}-\d{7}/);
            if (idMatch) order.orderId = idMatch[0];

            if (order.products.length > 0) {
                results.push(order);
            }
        }

        return results;
    }""")

    items: list[OrderItem] = []
    for order in orders:
        order_date = _parse_date(order.get("date", ""))
        if not order_date:
            continue

        total = _parse_amount(order.get("total", ""))
        order_id = order.get("orderId", "")
        products = order.get("products", [])

        if not products:
            continue

        per_item = total / len(products) if total else Decimal("0")

        for name in products:
            items.append(
                OrderItem(
                    order_date=order_date,
                    vendor="Amazon",
                    product_name=name,
                    amount=per_item,
                    order_id=order_id,
                    source=Source.AMAZON,
                )
            )

    return items


def _parse_date(text: str) -> date | None:
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_amount(text: str) -> Decimal | None:
    cleaned = re.sub(r"[¥￥円,\s]", "", text)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
