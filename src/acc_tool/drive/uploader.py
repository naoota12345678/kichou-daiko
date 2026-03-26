"""Googleドライブアップロード"""

from __future__ import annotations

import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_PATH = Path.home() / ".acc-tool" / "token.json"
CREDENTIALS_PATH = Path.home() / ".acc-tool" / "credentials.json"


def authenticate(credentials_path: Path | None = None) -> Credentials:
    """Google OAuth2認証を実行しトークンを返す

    初回はブラウザが開いて認証フロー。
    2回目以降は保存済みトークンを使用。
    """
    creds_file = credentials_path or CREDENTIALS_PATH
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    creds: Credentials | None = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
        else:
            if not creds_file.exists():
                raise FileNotFoundError(
                    f"Google OAuth認証情報ファイルが見つかりません: {creds_file}\n"
                    "Google Cloud Consoleからダウンロードして配置してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())

    return creds


def upload_file(
    local_path: Path,
    drive_filename: str,
    folder_id: str,
    creds: Credentials | None = None,
    mime_type: str | None = None,
) -> str:
    """ファイルをGoogleドライブにアップロード

    Args:
        local_path: アップロードするローカルファイル
        drive_filename: ドライブ上のファイル名
        folder_id: アップロード先フォルダID
        creds: 認証情報 (Noneなら自動取得)
        mime_type: MIMEタイプ

    Returns:
        アップロードされたファイルのID
    """
    if creds is None:
        creds = authenticate()

    service = build("drive", "v3", credentials=creds)

    file_metadata = {"name": drive_filename, "parents": [folder_id]}

    if mime_type is None:
        suffix = local_path.suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".csv": "text/csv",
        }
        mime_type = mime_map.get(suffix, "application/octet-stream")

    media = MediaFileUpload(str(local_path), mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    return file["id"]


def ensure_folder(folder_name: str, parent_id: str, creds: Credentials | None = None) -> str:
    """フォルダが存在しなければ作成し、フォルダIDを返す"""
    if creds is None:
        creds = authenticate()

    service = build("drive", "v3", credentials=creds)

    # 既存フォルダを検索
    query = (
        f"name='{folder_name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # 作成
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def list_files(folder_id: str, creds: Credentials | None = None) -> list[str]:
    """フォルダ内のファイル名一覧を取得（重複チェック用）"""
    if creds is None:
        creds = authenticate()

    service = build("drive", "v3", credentials=creds)

    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(name)", pageSize=1000).execute()
    return [f["name"] for f in results.get("files", [])]
