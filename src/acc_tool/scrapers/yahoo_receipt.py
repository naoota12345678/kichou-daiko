"""Yahoo Shopping receipt PDF downloader

Downloads order receipts/invoices as PDFs for each order.
Saves with e-document-compliant filename and folder structure.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

from acc_tool.drive.namer import generate_filename, generate_folder_path
from acc_tool.models import OrderItem, Source
from acc_tool.scrapers.yahoo_scraper import STATE_FILE, ORDER_HISTORY_URL


def download_receipts(
    items: list[OrderItem],
    output_dir: Path,
    fiscal_year_start_month: int = 4,
    headless: bool = False,
) -> list[Path]:
    """Download receipt PDFs for Yahoo Shopping orders

    Args:
        items: Order data list (order_id required for direct linking)
        output_dir: Root directory to save PDFs
        fiscal_year_start_month: Fiscal year start month (default 4 = April)
        headless: Run browser in headless mode

    Returns:
        List of saved PDF file paths
    """
    saved: list[Path] = []

    # Group by order_id (one order may have multiple items)
    orders_by_id: dict[str, list[OrderItem]] = {}
    no_id_items: list[OrderItem] = []
    for item in items:
        if item.order_id:
            orders_by_id.setdefault(item.order_id, []).append(item)
        else:
            no_id_items.append(item)

    if not orders_by_id and not no_id_items:
        print("[!] No orders found. Cannot download receipts.")
        return saved

    if not orders_by_id:
        print("[!] No order IDs found. Cannot download receipts.")
        print("    Receipts require order IDs from the scraper.")
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
            print("[!] No saved session. Run 'fetch-yahoo' first to log in.")
            browser.close()
            return saved

        page = context.new_page()

        for i, (order_id, order_items) in enumerate(orders_by_id.items(), 1):
            first_item = order_items[0]
            product_names = [it.product_name for it in order_items]
            if len(product_names) == 1:
                combined_name = product_names[0]
            else:
                combined_name = f"{product_names[0]} and {len(product_names) - 1} more"

            print(f"  [{i}/{len(orders_by_id)}] {order_id}: {combined_name[:40]}...")

            # Create output folder
            folder_path = generate_folder_path(
                fiscal_year_start_month,
                first_item.order_date.year,
                first_item.order_date.month,
            )
            save_dir = output_dir / folder_path
            save_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            receipt_item = OrderItem(
                order_date=first_item.order_date,
                vendor=first_item.vendor or "Yahoo Shopping",
                product_name=combined_name,
                amount=sum(it.amount for it in order_items),
                invoice_number=first_item.invoice_number,
                source=Source.YAHOO,
            )
            filename = generate_filename(receipt_item, ext=".pdf")
            save_path = save_dir / filename

            # Skip if already exists
            if save_path.exists():
                print(f"    -> skip (already exists)")
                saved.append(save_path)
                continue

            # Download receipt PDF
            try:
                pdf_path = _download_order_receipt(page, order_id, save_path)
                if pdf_path:
                    saved.append(pdf_path)
                    print(f"    -> saved: {pdf_path.name}")
                else:
                    print(f"    -> [!] failed to save")
            except Exception as e:
                print(f"    -> [!] error: {e}")

            time.sleep(1)

        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n[OK] {len(saved)}/{len(orders_by_id)} receipts saved to {output_dir}")
    return saved


def _download_order_receipt(page: Page, order_id: str, save_path: Path) -> Path | None:
    """Download receipt for a single order as PDF

    Tries multiple strategies:
    1. Navigate to order detail page and find receipt/invoice link
    2. Print the order detail page directly as PDF
    """
    # Build order detail URL
    # Yahoo Shopping uses different URL patterns - try common ones
    detail_urls = [
        f"https://order.shopping.yahoo.co.jp/order/list/detail?orderId={order_id}",
        f"https://order.shopping.yahoo.co.jp/order/list?orderId={order_id}",
    ]

    loaded = False
    for detail_url in detail_urls:
        try:
            page.goto(detail_url, wait_until="networkidle", timeout=60000)
            loaded = True
            break
        except Exception:
            try:
                page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                loaded = True
                break
            except Exception:
                continue

    if not loaded:
        # Fall back to order history page
        try:
            page.goto(ORDER_HISTORY_URL, wait_until="networkidle", timeout=60000)
        except Exception:
            page.goto(ORDER_HISTORY_URL, wait_until="domcontentloaded", timeout=30000)

    time.sleep(2)

    # Look for receipt/invoice link
    receipt_link = None
    receipt_selectors = [
        'a[href*="receipt"]',
        'a[href*="invoice"]',
        'a[href*="nouhin"]',
        'a[href*="ryoushu"]',
    ]
    for sel in receipt_selectors:
        try:
            receipt_link = page.query_selector(sel)
            if receipt_link:
                break
        except Exception:
            pass

    # Try text-based search
    if not receipt_link:
        try:
            receipt_link = page.query_selector(
                'a:has-text("領収書"), a:has-text("納品書"), a:has-text("invoice")'
            )
        except Exception:
            pass

    if receipt_link:
        try:
            receipt_link.click()
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(1)

            # Handle new tab
            pages = page.context.pages
            target_page = pages[-1] if len(pages) > 1 else page

            target_page.pdf(path=str(save_path), format="A4", print_background=True)

            if target_page != page and len(pages) > 1:
                target_page.close()

            return save_path
        except Exception:
            pass

    # Fallback: print the current order detail page as PDF
    try:
        page.pdf(path=str(save_path), format="A4", print_background=True)
        return save_path
    except Exception:
        return None
