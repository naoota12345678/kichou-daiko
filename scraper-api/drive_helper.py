"""Google Drive ヘルパー — 新フォルダ構成 + CSV積み上げ方式

フォルダ構成:
  acc/{年度}年度/{月}月/amazon/  ← PDF
  acc/{年度}年度/{月}月/楽天/    ← PDF
  acc/{年度}年度/{月}月/yahoo/   ← PDF
  acc/{年度}年度/{月}月/カード領収書/
  acc/{年度}年度/{月}月/現金領収書/
  acc/{年度}年度/{月}月/amazon.csv  ← 積み上げCSV
  acc/{年度}年度/{月}月/楽天.csv
  ...
"""

from __future__ import annotations

import csv
import io
import os
import json
import tempfile
from datetime import date
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload

from models import OrderItem

# ソース名 → フォルダ名のマッピング
SOURCE_FOLDER_MAP = {
    "Amazon": "amazon",
    "楽天": "楽天",
    "Yahoo": "yahoo",
    "Yahoo Shopping": "yahoo",
    "カード": "カード領収書",
    "現金": "現金領収書",
    "レシート": "現金領収書",
}

# ソース名 → CSV名のマッピング
SOURCE_CSV_MAP = {
    "Amazon": "amazon.csv",
    "楽天": "楽天.csv",
    "Yahoo": "yahoo.csv",
    "Yahoo Shopping": "yahoo.csv",
    "カード": "カード.csv",
    "現金": "現金.csv",
    "レシート": "現金.csv",
}


def _get_credentials(refresh_token: str) -> Credentials:
    """refresh tokenからCredentialsを生成"""
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        token_uri="https://oauth2.googleapis.com/token",
    )


def _ensure_folder(service, name: str, parent_id: str) -> str:
    """フォルダを検索or作成"""
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def _get_month_folder(service, root_id: str, fiscal_year_start_month: int, year: int, month: int) -> str:
    """acc/{年度}年度/{月}月 フォルダを確保して返す"""
    fiscal_year = year - 1 if month < fiscal_year_start_month else year
    year_folder = _ensure_folder(service, f"{fiscal_year}年度", root_id)
    month_folder = _ensure_folder(service, f"{month}月", year_folder)
    return month_folder


def _get_source_folder(service, month_folder_id: str, source: str) -> str:
    """月フォルダ内のソース別フォルダを確保して返す"""
    folder_name = SOURCE_FOLDER_MAP.get(source, source)
    return _ensure_folder(service, folder_name, month_folder_id)


def _find_file(service, name: str, parent_id: str) -> str | None:
    """フォルダ内のファイルをname検索してIDを返す"""
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType!='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def _download_file_content(service, file_id: str) -> str:
    """ファイルの中身をテキストで取得"""
    content = service.files().get_media(fileId=file_id).execute()
    if isinstance(content, bytes):
        return content.decode("utf-8-sig")
    return str(content)


def append_to_csv(
    service,
    month_folder_id: str,
    source: str,
    items: list[dict],
) -> str:
    """月フォルダ内のソース別CSVに行を追加

    CSVが存在しなければ新規作成。存在すれば既存の内容に追記。
    重複チェック: order_id + product_name が同じ行はスキップ。

    Returns:
        CSVファイル名
    """
    csv_name = SOURCE_CSV_MAP.get(source, f"{source}.csv")

    # 既存CSVを取得
    existing_file_id = _find_file(service, csv_name, month_folder_id)
    existing_rows: list[dict] = []
    existing_keys: set[str] = set()

    if existing_file_id:
        try:
            content = _download_file_content(service, existing_file_id)
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                existing_rows.append(row)
                key = f"{row.get('注文番号', '')}_{row.get('品名', '')}"
                existing_keys.add(key)
        except Exception as e:
            print(f"[CSV] Error reading existing CSV: {e}")

    # 新しい行を追加（重複スキップ）
    new_count = 0
    for item in items:
        key = f"{item.get('orderId', '')}_{item.get('productName', '')}"
        if key in existing_keys:
            continue

        existing_rows.append({
            "日付": item.get("orderDate", ""),
            "取引先": item.get("vendor", ""),
            "品名": item.get("productName", ""),
            "金額": str(item.get("amount", 0)),
            "勘定科目": item.get("account", ""),
            "注文番号": item.get("orderId", ""),
            "ソース": source,
        })
        existing_keys.add(key)
        new_count += 1

    if new_count == 0:
        print(f"[CSV] No new rows to add to {csv_name}")
        return csv_name

    # CSV文字列を生成
    buf = io.StringIO()
    fieldnames = ["日付", "取引先", "品名", "金額", "勘定科目", "注文番号", "ソース"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    # 日付でソート
    existing_rows.sort(key=lambda r: r.get("日付", ""))
    for row in existing_rows:
        writer.writerow(row)

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")

    # アップロード（既存があれば上書き、なければ新規作成）
    media = MediaInMemoryUpload(csv_bytes, mimetype="text/csv")

    if existing_file_id:
        service.files().update(
            fileId=existing_file_id, media_body=media
        ).execute()
    else:
        file_meta = {"name": csv_name, "parents": [month_folder_id]}
        service.files().create(
            body=file_meta, media_body=media, fields="id"
        ).execute()

    print(f"[CSV] {csv_name}: added {new_count} rows (total {len(existing_rows)})")
    return csv_name


def upload_receipt_and_update_csv(
    items: list[dict],
    receipts: list[dict],
    root_folder_id: str,
    refresh_token: str,
    fiscal_year_start_month: int = 4,
    source: str = "Amazon",
) -> list[str]:
    """領収書PDFをアップロードし、CSVに追記する

    Args:
        items: スクレイプしたアイテム一覧
        receipts: [{"orderId", "filename", "pdf", "orderDate"}, ...]
        root_folder_id: Driveルートフォルダ
        refresh_token: Drive refresh token
        fiscal_year_start_month: 会計年度開始月
        source: "Amazon" / "楽天" / "Yahoo"

    Returns:
        アップロードしたファイル名一覧
    """
    creds = _get_credentials(refresh_token)
    service = build("drive", "v3", credentials=creds)
    uploaded: list[str] = []

    # 月ごとにグループ化
    items_by_month: dict[tuple[int, int], list[dict]] = {}
    for item in items:
        d = item.get("orderDate", "").split("-")
        if len(d) >= 2:
            year, month = int(d[0]), int(d[1])
            items_by_month.setdefault((year, month), []).append(item)

    receipts_by_order: dict[str, dict] = {}
    for r in receipts:
        receipts_by_order[r["orderId"]] = r

    uploaded_order_ids = set()
    for (year, month), month_items in items_by_month.items():
        # 月フォルダ確保
        month_folder_id = _get_month_folder(
            service, root_folder_id, fiscal_year_start_month, year, month
        )

        # ソース別フォルダ確保
        source_folder_id = _get_source_folder(service, month_folder_id, source)
        for item in month_items:
            order_id = item.get("orderId", "")
            if order_id in uploaded_order_ids:
                continue
            receipt = receipts_by_order.get(order_id)
            if receipt and receipt.get("pdf"):
                try:
                    # 同名ファイルが既にあればスキップ
                    existing = _find_file(service, receipt["filename"], source_folder_id)
                    if not existing:
                        media = MediaInMemoryUpload(receipt["pdf"], mimetype="application/pdf")
                        file_meta = {"name": receipt["filename"], "parents": [source_folder_id]}
                        service.files().create(
                            body=file_meta, media_body=media, fields="id"
                        ).execute()
                        uploaded.append(receipt["filename"])
                        print(f"[Drive] Uploaded PDF: {receipt['filename']}")
                    else:
                        print(f"[Drive] Skip (exists): {receipt['filename']}")
                except Exception as e:
                    print(f"[Drive] PDF upload error: {e}")
                uploaded_order_ids.add(order_id)

        # CSVに追記
        try:
            # 勘定科目を推定
            from rules import classify_account
            from decimal import Decimal
            for item in month_items:
                account, _ = classify_account(
                    item.get("productName", ""),
                    Decimal(str(item.get("amount", 0)))
                )
                item["account"] = account

            csv_name = append_to_csv(service, month_folder_id, source, month_items)
            uploaded.append(csv_name)
        except Exception as e:
            print(f"[CSV] Error: {e}")

    return uploaded
