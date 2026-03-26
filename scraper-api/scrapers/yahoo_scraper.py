"""Yahoo Shopping order history scraper

odhistory.shopping.yahoo.co.jp from order history.
Login requires manual CAPTCHA solving.
"""

from __future__ import annotations

import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

from models import OrderItem, ParseResult, Source

ORDER_HISTORY_URL = "https://odhistory.shopping.yahoo.co.jp/order-history/list"
STATE_FILE = Path.home() / ".acc-tool" / "yahoo_session.json"


def scrape_yahoo(
    year: int | None = None,
    save_html_dir: Path | None = None,
    headless: bool = False,
) -> ParseResult:
    """Yahoo Shopping order history scraper"""
    all_items: list[OrderItem] = []
    errors: list[str] = []

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

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

        # Go to order history
        page.goto(ORDER_HISTORY_URL, wait_until="networkidle", timeout=60000)
        time.sleep(3)

        # Check if logged in by looking at page content
        if not _is_logged_in(page):
            print("")
            print("==========================================")
            print("  Not logged in. Opening Yahoo login page.")
            print("  Please log in AND solve CAPTCHA if shown.")
            print("  After login, order history will load.")
            print("  (waiting up to 5 minutes)")
            print("==========================================")
            print("")

            # Go to login with redirect to order history
            login_url = (
                "https://login.yahoo.co.jp/config/login"
                "?.src=shopping"
                "&.done=https%3A%2F%2Fodhistory.shopping.yahoo.co.jp%2Forder-history%2Flist"
            )
            page.goto(login_url, wait_until="networkidle", timeout=60000)

            # Wait until user logs in and reaches order history
            _wait_for_logged_in_order_page(page)
            context.storage_state(path=str(STATE_FILE))
            print("[OK] Login successful. Session saved.")

        print("[OK] Order history page loaded.")
        print(f"  URL: {page.url[:100]}")

        if save_html_dir:
            save_html_dir.mkdir(parents=True, exist_ok=True)
            (save_html_dir / "yahoo_list.html").write_text(
                page.content(), encoding="utf-8"
            )

        # Extract order data
        page_num = 1
        while True:
            print(f"  Page {page_num} ...")
            page_items = _extract_orders_from_page(page)
            all_items.extend(page_items)
            print(f"    -> {len(page_items)} orders")

            # Pagination
            next_btn = _find_next_button(page)
            if not next_btn:
                break
            next_btn.click()
            try:
                page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(3)
            page_num += 1

        # Dates and order IDs are extracted from body text, no detail page needed

        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n[OK] Total: {len(all_items)} orders")

    if not all_items:
        errors.append("No order data extracted.")

    return ParseResult(items=all_items, errors=errors, source=Source.YAHOO)


def _is_logged_in(page: Page) -> bool:
    """Check if we're on the order history page and logged in."""
    try:
        result = page.evaluate(r"""() => {
            const url = window.location.href;
            const body = document.body ? document.body.innerText : '';
            // Not logged in if we see the login prompt
            if (body.includes('\u30ed\u30b0\u30a4\u30f3\u304c\u5fc5\u8981')) return false;
            // Logged in if we see order dates or detail buttons
            if (/\d{4}\u5e74\d{1,2}\u6708\d{1,2}\u65e5/.test(body)) return true;
            if (body.includes('\u6ce8\u6587\u65e5')) return true;
            // Check for actual order content elements
            const hasDetailBtn = document.querySelectorAll(
                'form[action*="detail"], [onclick*="submitDetail"], a[href*="detail"]'
            ).length > 0;
            return hasDetailBtn;
        }""")
        return result
    except Exception:
        return False


def _wait_for_logged_in_order_page(page: Page, timeout_sec: int = 300) -> None:
    """Wait until user completes login + CAPTCHA, then navigate to order history.

    Yahoo login flow: login page -> CAPTCHA -> redirect (or stay on login domain).
    We detect success by checking if we left the login domain OR if the page
    no longer shows login/captcha content.
    """
    deadline = time.time() + timeout_sec
    prev_url = ""
    while time.time() < deadline:
        try:
            url = page.url
            if url != prev_url:
                print(f"  URL: {url[:100].encode('ascii','replace').decode()}")
                prev_url = url

            # Success: redirected to order history
            if "odhistory.shopping.yahoo.co.jp" in url:
                time.sleep(3)
                return

            # Success: left login domain entirely (went to shopping top, etc.)
            if "login.yahoo.co.jp" not in url and "yahoo.co.jp" in url:
                print("  Login completed - redirected away from login.")
                time.sleep(2)
                page.goto(ORDER_HISTORY_URL, wait_until="networkidle", timeout=60000)
                time.sleep(5)
                return

            # Success: still on login domain but page changed (e.g. login complete interim page)
            # Check body - if no login form and no captcha, might be success
            body_check = page.evaluate(r"""() => {
                const body = document.body ? document.body.innerText : '';
                const hasLoginForm = body.includes('\u30ed\u30b0\u30a4\u30f3') && body.includes('\u6b21\u3078');
                const hasCaptcha = body.includes('\u6587\u5b57\u8a8d\u8a3c');
                const isShort = body.length < 100;
                return { hasLoginForm, hasCaptcha, bodyLen: body.length, isShort };
            }""")
            # If body is very short or has neither login form nor captcha, login probably succeeded
            if (not body_check["hasLoginForm"] and
                not body_check["hasCaptcha"] and
                body_check["bodyLen"] > 10):
                print("  Login appears complete (no login/captcha content).")
                time.sleep(3)
                page.goto(ORDER_HISTORY_URL, wait_until="networkidle", timeout=60000)
                time.sleep(5)
                return

        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError("Login timed out.")


def _find_next_button(page: Page):
    """Find next page button."""
    for sel in ['a[rel="next"]', 'a:has-text(">")', 'a:has-text("Next")', 'li.next a']:
        try:
            btn = page.query_selector(sel)
            if btn:
                return btn
        except Exception:
            pass
    return None


def _extract_orders_from_page(page: Page) -> list[OrderItem]:
    """Extract items from the order history list page using body text parsing.

    Yahoo Shopping list page body text has a clear structure:
    - Date line: "2026年3月17日"
    - Product name lines
    - Price line: "3,698円"
    - "注文番号：" followed by "{store-id}-{order-number}"
    - Shop name line

    Multiple products under same order share the same date/order number.
    """
    body = page.evaluate("() => document.body ? document.body.innerText : ''")

    items: list[OrderItem] = []
    current_date: date | None = None
    current_order_id = ""
    current_store = ""

    # Split body text into order blocks by date headers
    # Pattern: "YYYY年M月D日" marks a new order group
    blocks = re.split(r'(?=\d{4}年\d{1,2}月\d{1,2}日)', body)

    for block in blocks:
        if not block.strip():
            continue

        # Extract date from block start
        date_match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', block.strip())
        if date_match:
            current_date = date(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
            )

        if not current_date:
            continue

        # Extract order number: "注文番号：\n{store-id}-{number}"
        order_match = re.search(r'注文番号[：:]\s*\n?\s*([\w\-]+)', block)
        if order_match:
            full_order_id = order_match.group(1)
            current_order_id = full_order_id
            # Store ID is the part before the number
            store_match = re.match(r'([a-zA-Z][\w\-]*?)-(\d+)$', full_order_id)
            if store_match:
                current_store = store_match.group(1)

        # Extract product + price pairs from this block
        # Products are listed as lines of text followed by "N,NNN円"
        lines = block.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check if next line (or a nearby line) has a price
            price_val = None
            product_name = None

            # Skip non-product lines
            if (not line or len(line) < 5 or
                line.startswith('注文') or line.startswith('再度') or
                line.startswith('お問い') or line.startswith('レビュー') or
                line.startswith('友だち') or line.startswith('ブロック') or
                line.startswith('最大') or line.startswith('領収書') or
                line.startswith('すべて見る') or line.startswith('一覧') or
                line.startswith('定期') or line.startswith('ふるさと') or
                line.startswith('カラー:') or line.startswith('サイズ:') or
                line.startswith('商品着用') or line.startswith('※') or
                line.startswith('ようこそ') or
                re.match(r'^\d{4}年', line) or
                re.match(r'^(注文確認中|発送済み|配達済み|キャンセル)', line) or
                line == '送料無料' or re.match(r'^送料\d', line) or
                # Skip option/selection lines: short "label:value" patterns
                re.match(r'^(種類|選択|色|東西在庫|印影確認|電子印鑑|納期|数量|配送)[:：（]', line) or
                # Skip note lines starting with ※
                (line.startswith('※') and ':' in line) or
                # Skip "現在在庫がない" etc.
                line.startswith('現在')):
                i += 1
                continue

            # Check if this line is followed by a price line (within next 6 lines)
            for j in range(i + 1, min(i + 7, len(lines))):
                next_line = lines[j].strip()
                price_match = re.match(r'^([\d,]+)円', next_line)
                if price_match:
                    product_name = line
                    price_val = price_match.group(1).replace(',', '')
                    break
                # Skip known non-product lines between product and price
                if (not next_line or
                    next_line.startswith('※') or
                    next_line.startswith('カラー') or next_line.startswith('サイズ') or
                    next_line.startswith('種類') or next_line.startswith('選択') or
                    next_line.startswith('電子') or next_line.startswith('印影') or
                    next_line.startswith('東西') or next_line.startswith('納期') or
                    next_line.startswith('送料') or next_line.startswith('商品着用') or
                    re.match(r'^[\w（）]+[:：]', next_line)):
                    continue
                # If we hit 再度購入 or 注文詳細, stop
                if next_line.startswith('再度') or next_line.startswith('注文'):
                    break

            if product_name and price_val:
                # Clean product name
                clean_name = re.sub(r'[\d,]+円.*$', '', product_name).strip()
                if len(clean_name) < 3:
                    clean_name = product_name

                items.append(
                    OrderItem(
                        order_date=current_date,
                        vendor=current_store or "Yahoo Shopping",
                        product_name=clean_name,
                        amount=Decimal(price_val),
                        order_id=current_order_id,
                        source=Source.YAHOO,
                    )
                )

            i += 1

    return items


def _enrich_with_detail_pages(
    page: Page, items: list[OrderItem], save_html_dir: Path | None
) -> None:
    """Navigate to each order's detail page to get date and order ID.

    Yahoo uses form POST (submitDetailButtonForm) to reach detail pages.
    We find and click the detail buttons on the list page.
    """
    # Go back to the list page first
    page.goto(ORDER_HISTORY_URL, wait_until="networkidle", timeout=60000)
    time.sleep(3)

    # Find detail buttons/forms
    detail_forms = page.evaluate(r"""() => {
        const forms = [];
        // Look for forms that go to detail pages
        document.querySelectorAll('form').forEach(f => {
            const action = f.action || '';
            if (action.includes('detail') || f.id.includes('detail')) {
                const inputs = {};
                f.querySelectorAll('input[type="hidden"]').forEach(inp => {
                    inputs[inp.name] = inp.value;
                });
                forms.push({ action: action.slice(0, 200), id: f.id, inputs });
            }
        });

        // Also look for buttons with onclick containing submitDetailButtonForm
        document.querySelectorAll('[onclick*="submitDetail"]').forEach(el => {
            const onclick = el.getAttribute('onclick') || '';
            const m = onclick.match(/submitDetailButtonForm\(['"]([^'"]+)['"]\)/);
            if (m) {
                forms.push({ orderId: m[1], onclick: onclick.slice(0, 200) });
            }
        });

        // Also check for direct links to detail pages
        document.querySelectorAll('a[href*="order-history/detail"]').forEach(a => {
            forms.push({ href: a.href.slice(0, 200), text: a.textContent.trim().slice(0, 50) });
        });

        return forms;
    }""")

    print(f"    Found {len(detail_forms)} detail entries")

    if not detail_forms:
        print("    No detail forms/links found. Dates will use today's date.")
        return

    # For each detail form, navigate and extract date + order ID
    for i, form_info in enumerate(detail_forms):
        if i >= len(items):
            break

        try:
            order_id = form_info.get("orderId", "")
            href = form_info.get("href", "")

            if order_id:
                # Use JS to submit the form
                page.evaluate(f"YAHOO.JP.shp.order.submitDetailButtonForm('{order_id}')")
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(2)
            elif href:
                page.goto(href, wait_until="networkidle", timeout=30000)
                time.sleep(2)
            else:
                continue

            # Extract date and order ID from detail page
            detail = page.evaluate(r"""() => {
                const body = document.body ? document.body.innerText : '';
                const result = {};
                // Date
                const dm = body.match(/(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5/) ||
                           body.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
                if (dm) result.date = dm[0];
                // Order ID / number
                const im = body.match(/\u6ce8\u6587\u756a\u53f7[^\d]*(\d{8,})/);
                if (im) result.orderId = im[1];
                else {
                    const im2 = body.match(/\b(\d{12,20})\b/);
                    if (im2) result.orderId = im2[1];
                }
                return result;
            }""")

            if detail.get("date"):
                d = _parse_date(detail["date"])
                if d:
                    items[i].order_date = d
            if detail.get("orderId"):
                items[i].order_id = detail["orderId"]

            print(f"    [{i+1}] date={detail.get('date','?')} id={detail.get('orderId','?')}")

            if save_html_dir:
                (save_html_dir / f"yahoo_detail_{i+1}.html").write_text(
                    page.content(), encoding="utf-8"
                )

            # Go back to list
            page.go_back()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(2)

        except Exception as e:
            print(f"    [{i+1}] error: {e}")


def _parse_date(text: str) -> date | None:
    m = re.search(r"(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_amount(text: str) -> Decimal | None:
    if not text:
        return None
    cleaned = re.sub(r"[¥￥円,\s]", "", text)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
