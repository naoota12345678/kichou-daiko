"""Amazon領収書PDF取得

注文履歴から各注文の領収書/購入明細書をPDFとして保存。
電帳法準拠のファイル名・フォルダ構成で保存する。
"""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, BrowserContext

from namer import generate_filename, generate_folder_path
from models import OrderItem, Source
from scrapers.amazon_scraper import STATE_FILE, ORDER_HISTORY_URL

INVOICE_URL = "https://www.amazon.co.jp/gp/digital/your-account/order-summary.html?orderID={order_id}"


def download_receipts(
    items: list[OrderItem],
    output_dir: Path,
    fiscal_year_start_month: int = 4,
    headless: bool = False,
) -> list[Path]:
    """注文データの領収書PDFをダウンロード

    Args:
        items: 注文データ一覧 (order_idが必要)
        output_dir: 保存先ルートディレクトリ
        fiscal_year_start_month: 会計年度開始月
        headless: ヘッドレスモード

    Returns:
        保存されたPDFファイルのパス一覧
    """
    saved: list[Path] = []

    # order_idでグループ化（同一注文に複数商品がある場合）
    orders_by_id: dict[str, list[OrderItem]] = {}
    no_id_items: list[OrderItem] = []
    for item in items:
        if item.order_id:
            orders_by_id.setdefault(item.order_id, []).append(item)
        else:
            no_id_items.append(item)

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
            print("[!] No saved session. Run 'fetch-amazon' first to log in.")
            browser.close()
            return saved

        page = context.new_page()

        for i, (order_id, order_items) in enumerate(orders_by_id.items(), 1):
            first_item = order_items[0]
            # 品名（複数商品ある場合は最初の商品名）
            product_names = [it.product_name for it in order_items]
            combined_name = product_names[0] if len(product_names) == 1 else f"{product_names[0]} ほか{len(product_names)-1}点"

            print(f"  [{i}/{len(orders_by_id)}] {order_id}: {combined_name[:40]}...")

            # フォルダ作成
            folder_path = generate_folder_path(
                fiscal_year_start_month,
                first_item.order_date.year,
                first_item.order_date.month,
            )
            save_dir = output_dir / folder_path
            save_dir.mkdir(parents=True, exist_ok=True)

            # ファイル名生成
            receipt_item = OrderItem(
                order_date=first_item.order_date,
                vendor="Amazon",
                product_name=combined_name,
                amount=sum(it.amount for it in order_items),
                invoice_number=first_item.invoice_number,
                source=Source.AMAZON,
            )
            filename = generate_filename(receipt_item, ext=".pdf")
            save_path = save_dir / filename

            # 既に存在する場合はスキップ
            if save_path.exists():
                print(f"    -> skip (already exists)")
                saved.append(save_path)
                continue

            # 領収書ページを開いてPDF保存
            try:
                pdf_path = _download_order_receipt(page, order_id, save_path)
                if pdf_path:
                    saved.append(pdf_path)
                    print(f"    -> saved: {pdf_path.name}")
                else:
                    print(f"    -> [!] failed to save")
            except Exception as e:
                print(f"    -> [!] error: {e}")

            time.sleep(1)  # Amazonに負荷をかけすぎない

        # セッション更新
        context.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\n[OK] {len(saved)}/{len(orders_by_id)} receipts saved to {output_dir}")
    return saved


def _download_order_receipt(page: Page, order_id: str, save_path: Path) -> Path | None:
    """1件の注文の領収書をPDFとして保存"""

    # 方法1: 注文詳細ページから領収書リンクを探す
    detail_url = f"https://www.amazon.co.jp/gp/your-account/order-details?orderID={order_id}"
    page.goto(detail_url, wait_until="networkidle")
    time.sleep(2)

    # 「領収書/購入明細書」リンクを探す
    receipt_link = page.query_selector(
        'a[href*="invoice"], a[href*="receipt"], '
        'a:has-text("領収書"), a:has-text("購入明細書")'
    )

    if receipt_link:
        receipt_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # 新しいタブで開いた場合
        pages = page.context.pages
        target_page = pages[-1] if len(pages) > 1 else page

        # PDFとして保存
        target_page.pdf(path=str(save_path), format="A4", print_background=True)

        # 別タブなら閉じる
        if target_page != page and len(pages) > 1:
            target_page.close()

        return save_path

    # 方法2: 注文詳細ページ自体をPDFにする
    page.pdf(path=str(save_path), format="A4", print_background=True)
    return save_path
