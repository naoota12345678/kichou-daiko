"""Google Driveへのレシート画像アップロード"""

import io
import os
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

ROOT_FOLDER_ID = os.environ.get(
    "DRIVE_ROOT_FOLDER_ID", "0AN0FWbtRJPmtUk9PVA"
)

_service = None


def _get_service():
    global _service
    if _service:
        return _service

    sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        import json
        info = json.loads(sa_json)
        cred = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive"]
        )
    elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        cred = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
            scopes=["https://www.googleapis.com/auth/drive"],
        )
    else:
        import google.auth
        cred, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])

    _service = build("drive", "v3", credentials=cred, cache_discovery=False)
    return _service


def _sanitize(name: str) -> str:
    """ファイル名に使えない文字を置換"""
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()


def _find_or_create_folder(name: str, parent_id: str) -> str:
    """指定フォルダ内にサブフォルダを探す。なければ作成"""
    service = _get_service()
    safe_name = _sanitize(name)

    q = (
        f"'{parent_id}' in parents "
        f"and name = '{safe_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(q=q, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta = {
        "name": safe_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return folder["id"]


def upload_receipt_to_drive(
    image_bytes: bytes,
    client_name: str,
    receipt_date: str,
    filename: str,
    payment_method: str = "現金",
    content_type: str = "image/jpeg",
) -> dict:
    """
    レシート画像をGoogle Driveにアップロード

    フォルダ構成:
      レシートアプリ / 顧問先名 / YYYY-MM / 現金 or カード / ファイル名
    """
    service = _get_service()

    # 顧問先フォルダ
    client_folder_id = _find_or_create_folder(client_name, ROOT_FOLDER_ID)

    # 月別フォルダ (YYYY-MM)
    if receipt_date and len(receipt_date) >= 7:
        month_str = receipt_date[:7]  # "2026-03"
    else:
        from datetime import date
        month_str = date.today().strftime("%Y-%m")

    month_folder_id = _find_or_create_folder(month_str, client_folder_id)

    # 現金/カードフォルダ
    payment_folder = "カード" if payment_method == "カード" else "現金"
    month_folder_id = _find_or_create_folder(payment_folder, month_folder_id)

    # アップロード
    safe_filename = _sanitize(filename)
    media = MediaIoBaseUpload(
        io.BytesIO(image_bytes), mimetype=content_type, resumable=False
    )
    meta = {
        "name": safe_filename,
        "parents": [month_folder_id],
    }
    uploaded = service.files().create(
        body=meta, media_body=media, fields="id,webViewLink", supportsAllDrives=True
    ).execute()

    return {
        "file_id": uploaded["id"],
        "url": uploaded.get("webViewLink", ""),
        "month_folder_id": month_folder_id,
        "client_folder_id": client_folder_id,
    }


def append_to_csv(
    client_name: str,
    receipt_date: str,
    payment_method: str,
    row_data: dict,
) -> None:
    """
    月別フォルダ内のCSVファイルにデータを追記
    現金.csv / カード.csv に分けて保存
    """
    import csv

    service = _get_service()

    # フォルダ階層を辿る
    client_folder_id = _find_or_create_folder(client_name, ROOT_FOLDER_ID)

    if receipt_date and len(receipt_date) >= 7:
        month_str = receipt_date[:7]
    else:
        from datetime import date
        month_str = date.today().strftime("%Y-%m")

    month_folder_id = _find_or_create_folder(month_str, client_folder_id)

    # CSVファイル名
    payment_label = "カード" if payment_method == "カード" else "現金"
    csv_filename = f"{payment_label}.csv"

    # 既存CSVを探す
    q = (
        f"'{month_folder_id}' in parents "
        f"and name = '{csv_filename}' "
        f"and mimeType != 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(
        q=q, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    existing = results.get("files", [])

    headers = ["日付", "取引先", "金額", "借方科目", "貸方科目", "税率", "摘要", "確信度"]

    if existing:
        # 既存CSVをダウンロードして追記
        file_id = existing[0]["id"]
        content = service.files().get_media(
            fileId=file_id, supportsAllDrives=True
        ).execute().decode("utf-8-sig")

        output = io.StringIO()
        output.write("\ufeff")
        output.write(content.lstrip("\ufeff"))

        writer = csv.writer(output)
        writer.writerow([
            row_data.get("date", ""),
            row_data.get("vendor", ""),
            row_data.get("amount", ""),
            row_data.get("debit_account", ""),
            row_data.get("credit_account", ""),
            row_data.get("tax_rate", ""),
            row_data.get("description", ""),
            row_data.get("confidence", ""),
        ])

        media = MediaIoBaseUpload(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv", resumable=False
        )
        service.files().update(
            fileId=file_id, media_body=media, supportsAllDrives=True
        ).execute()
    else:
        # 新規CSV作成
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerow([
            row_data.get("date", ""),
            row_data.get("vendor", ""),
            row_data.get("amount", ""),
            row_data.get("debit_account", ""),
            row_data.get("credit_account", ""),
            row_data.get("tax_rate", ""),
            row_data.get("description", ""),
            row_data.get("confidence", ""),
        ])

        meta = {
            "name": csv_filename,
            "parents": [month_folder_id],
        }
        media = MediaIoBaseUpload(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv", resumable=False
        )
        service.files().create(
            body=meta, media_body=media, fields="id", supportsAllDrives=True
        ).execute()
