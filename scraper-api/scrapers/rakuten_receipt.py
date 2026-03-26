"""Rakuten receipt PDF downloader

Navigate to each order's detail page and save as PDF.
Uses the detail_url from the scraper's order summary data.
"""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

from namer import generate_filename, generate_folder_path
from models import OrderItem, Source
from scrapers.rakuten_scraper import STATE_FILE

# Detail page URL format (from order list's detail links)
DETAIL_URL_TEMPLATE = (
    "https://order.my.rakuten.co.jp/purchase-history/"
    "?order_number={order_id}&shop_id={shop_id}&act=detail_page_view"
)


def download_receipts(
    items: list[OrderItem],
    output_dir: Path,
    fiscal_year_start_month: int = 4,
    headless: bool = False,
) -> list[Path]:
    """Download receipt PDFs for each order by visiting detail pages."""
    saved: list[Path] = []

    # Group by order_id
    orders_by_id: dict[str, list[OrderItem]] = {}
    for item in items:
        if item.order_id:
            orders_by_id.setdefault(item.order_id, []).append(item)

    if not orders_by_id:
        print("[!] No order IDs found. Cannot download receipts.")
        return saved

    print(f"Downloading receipts for {len(orders_by_id)} orders...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        if STATE_FILE.exists():
            context = browser.new_context(
                storage_state=str(STATE_FILE),
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )
        else:
            print("[!] No saved session. Run 'fetch-rakuten' first.")
            browser.close()
            return saved

        page = context.new_page()

        for i, (order_id, order_items) in enumerate(orders_by_id.items(), 1):
            first_item = order_items[0]
            product_names = [it.product_name for it in order_items]
            combined_name = (
                product_names[0]
                if len(product_names) == 1
                else f"{product_names[0]} + {len(product_names) - 1} more"
            )

            print(f"  [{i}/{len(orders_by_id)}] {order_id}: {combined_name[:40]}...")

            folder_path = generate_folder_path(
                fiscal_year_start_month,
                first_item.order_date.year,
                first_item.order_date.month,
            )
            save_dir = output_dir / folder_path
            save_dir.mkdir(parents=True, exist_ok=True)

            receipt_item = OrderItem(
                order_date=first_item.order_date,
                vendor=first_item.vendor,
                product_name=combined_name,
                amount=sum(it.amount for it in order_items),
                source=Source.RAKUTEN,
            )
            filename = generate_filename(receipt_item, ext=".pdf")
            save_path = save_dir / filename

            if save_path.exists():
                print(f"    -> skip (already exists)")
                saved.append(save_path)
                continue

            try:
                pdf_path = _download_order_receipt(page, order_id, save_path)
                if pdf_path:
                    saved.append(pdf_path)
                    print(f"    -> saved: {pdf_path.name}")
                else:
                    print(f"    -> [!] failed")
            except Exception as e:
                print(f"    -> [!] error: {e}")

            time.sleep(1)

        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n[OK] {len(saved)}/{len(orders_by_id)} receipts saved to {output_dir}")
    return saved


def _download_order_receipt(page: Page, order_id: str, save_path: Path) -> Path | None:
    """Navigate to order detail page and save as PDF.

    The detail page URL uses the order_number and shop_id from the order list.
    shop_id is the first numeric segment of the order_id.
    """
    # Extract shop_id from order_id (format: shopid-YYYYMMDD-seqnum)
    parts = order_id.split("-")
    shop_id = parts[0] if parts else ""

    detail_url = DETAIL_URL_TEMPLATE.format(order_id=order_id, shop_id=shop_id)

    try:
        page.goto(detail_url, wait_until="networkidle", timeout=60000)
    except Exception:
        page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)

    time.sleep(3)

    # Verify we're on a detail page (not the list page)
    url = page.url
    body_len = page.evaluate("() => (document.body.innerText || '').length")

    # Save the detail page as PDF
    page.pdf(path=str(save_path), format="A4", print_background=True)
    return save_path
