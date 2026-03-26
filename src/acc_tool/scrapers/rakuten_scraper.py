"""Rakuten order history scraper

1. List page: get order dates, order IDs, detail URLs
2. Detail pages: get product names, prices, shop names
Session is saved and reused on subsequent runs.
"""

from __future__ import annotations

import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

from acc_tool.models import OrderItem, ParseResult, Source

ORDER_HISTORY_URL = "https://order.my.rakuten.co.jp/"
STATE_FILE = Path.home() / ".acc-tool" / "rakuten_session.json"

_LOGIN_URL_PATTERNS = [
    "grp01.id.rakuten.co.jp",
    "login.account.rakuten.com",
]


def scrape_rakuten(
    year: int | None = None,
    save_html_dir: Path | None = None,
    headless: bool = False,
) -> ParseResult:
    """Scrape Rakuten order history: list page -> detail pages."""
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

        # Navigate to order history
        url = ORDER_HISTORY_URL
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)

        current_url = page.url
        print(f"  URL: {current_url[:120]}")

        # Login if needed
        if any(pat in current_url for pat in _LOGIN_URL_PATTERNS):
            print("")
            print("========================================")
            print("  Browser window is open.")
            print("  Please log in to Rakuten.")
            print("  (waiting up to 5 minutes)")
            print("========================================")
            print("")
            _wait_for_order_history(page)
            context.storage_state(path=str(STATE_FILE))
            print("[OK] Login successful. Session saved for next time.")

        print("[OK] Order history page loaded.")

        # Select year filter if specified
        if year:
            _select_year(page, year)

        # Step 1: Collect order summaries from list page
        print("  Collecting order list...")
        order_summaries = _collect_order_summaries(page)
        print(f"  -> {len(order_summaries)} orders found on list page")

        if save_html_dir:
            save_html_dir.mkdir(parents=True, exist_ok=True)
            (save_html_dir / "rakuten_list.html").write_text(
                page.content(), encoding="utf-8"
            )

        # Step 2: Visit each detail page to get product names and prices
        for i, summary in enumerate(order_summaries, 1):
            print(f"  [{i}/{len(order_summaries)}] {summary['order_id'][:30]}...")

            try:
                detail_items = _scrape_detail_page(
                    page, summary, save_html_dir, i
                )
                all_items.extend(detail_items)
                names = [it.product_name[:30] for it in detail_items]
                amounts = [str(it.amount_int) for it in detail_items]
                print(f"    -> {len(detail_items)} items, {', '.join(amounts)}")
            except Exception as e:
                print(f"    -> [!] error: {e}")
                errors.append(f"Order {summary['order_id']}: {e}")

            time.sleep(1)  # Be nice to Rakuten

        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n[OK] Total: {len(all_items)} items from {len(order_summaries)} orders")

    if not all_items:
        errors.append("No order data extracted.")

    return ParseResult(items=all_items, errors=errors, source=Source.RAKUTEN)


def _wait_for_order_history(page: Page, timeout_sec: int = 300) -> None:
    """Wait for order history content (DOM-based)."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            has_orders = page.evaluate(r"""() => {
                const body = document.body ? document.body.innerText : '';
                const hasDate = /\d{4}\/\d{1,2}\/\d{1,2}/.test(body);
                const hasOrderLabel = body.includes('\u6ce8\u6587\u756a\u53f7') ||
                                      body.includes('\u6ce8\u6587\u65e5');
                return hasDate && hasOrderLabel;
            }""")
            if has_orders:
                print("  [OK] Order history detected.")
                time.sleep(2)
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError("Login timed out.")


def _select_year(page: Page, year: int) -> None:
    """Select year in the purchase history filter."""
    try:
        select = page.query_selector('select[name="year"]')
        if select:
            select.select_option(str(year))
            time.sleep(1)
            # Click search/filter button if there is one
            btn = page.query_selector(
                'button[type="submit"], button:has-text("検索"), '
                'input[type="submit"]'
            )
            if btn:
                btn.click()
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)
            print(f"  [OK] Year filter: {year}")
    except Exception as e:
        print(f"  [!] Year filter failed: {e}")


def _collect_order_summaries(page: Page) -> list[dict]:
    """Extract order date, order_id, detail_url from list page."""
    summaries = page.evaluate(r"""() => {
        const results = [];
        const seen = new Set();

        // Find all detail links
        const links = document.querySelectorAll('a[href*="act=detail_page_view"]');
        for (const link of links) {
            const href = link.href || link.getAttribute('href') || '';
            // Extract order_number from URL
            const m = href.match(/order_number=([^&]+)/);
            if (!m) continue;
            const orderId = m[1];
            if (seen.has(orderId)) continue;
            seen.add(orderId);

            // Find the parent order block
            let block = link.closest(
                '[class*="spacer"], [class*="block"], [class*="order"]'
            ) || link.parentElement.parentElement.parentElement;

            const blockText = block ? block.textContent : '';

            // Extract date from the block
            const dm = blockText.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
            const dateStr = dm ? dm[0] : '';

            results.push({
                order_id: orderId,
                date: dateStr,
                detail_url: href,
            });
        }

        return results;
    }""")
    return summaries


def _scrape_detail_page(
    page: Page,
    summary: dict,
    save_html_dir: Path | None,
    index: int,
) -> list[OrderItem]:
    """Navigate to order detail page and extract from __INITIAL_STATE__ JSON."""
    detail_url = summary.get("detail_url", "")
    if not detail_url:
        return []

    page.goto(detail_url, wait_until="networkidle", timeout=60000)
    time.sleep(2)

    if save_html_dir:
        (save_html_dir / f"rakuten_detail_{index}.html").write_text(
            page.content(), encoding="utf-8"
        )

    # Extract structured data from React's __INITIAL_STATE__
    data = page.evaluate(r"""() => {
        try {
            const state = window.__INITIAL_STATE__;
            if (!state || !state.orderData) return null;

            const od = state.orderData;
            const summary = od.orderSummary || {};
            const itemObj = od.itemObject || {};
            const items = itemObj.itemList || [];

            return {
                shop: summary.shopName || '',
                totalPrice: itemObj.paymentAmount || summary.totalPrice || 0,
                orderDate: summary.orderCreationDate || '',
                orderNumber: summary.orderNumber || '',
                items: items.map(it => ({
                    name: it.itemName || '',
                    price: it.price || 0,
                    units: it.units || 1,
                })),
            };
        } catch(e) {
            return null;
        }
    }""")

    if not data:
        return []

    order_date = _parse_date(data.get("orderDate", "") or summary.get("date", ""))
    if not order_date:
        return []

    order_id = data.get("orderNumber", "") or summary.get("order_id", "")
    shop = (data.get("shop") or "").strip() or "楽天"
    json_items = data.get("items", [])
    total_price = data.get("totalPrice", 0)

    items: list[OrderItem] = []

    if json_items:
        for jitem in json_items:
            price = jitem.get("price", 0)
            units = jitem.get("units", 1)
            items.append(
                OrderItem(
                    order_date=order_date,
                    vendor=shop,
                    product_name=jitem.get("name", "(unknown)"),
                    amount=Decimal(str(price * units)) if price else Decimal("0"),
                    order_id=order_id,
                    source=Source.RAKUTEN,
                )
            )
    elif total_price:
        items.append(
            OrderItem(
                order_date=order_date,
                vendor=shop,
                product_name="(detail)",
                amount=Decimal(str(total_price)),
                order_id=order_id,
                source=Source.RAKUTEN,
            )
        )

    return items


def _parse_date(text: str) -> date | None:
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_amount_str(text: str) -> Decimal | None:
    if not text:
        return None
    cleaned = re.sub(r"[¥￥円,\s]", "", text)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
