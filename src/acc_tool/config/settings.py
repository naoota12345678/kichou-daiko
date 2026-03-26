"""設定の読み込み"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class AppSettings:
    google_client_id: str = ""
    google_client_secret: str = ""
    drive_folder_id: str = ""
    fiscal_year_start_month: int = 4


def load(env_path: Path | None = None) -> AppSettings:
    """環境変数から設定を読み込む"""
    load_dotenv(env_path or Path.cwd() / ".env")

    return AppSettings(
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        drive_folder_id=os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""),
        fiscal_year_start_month=int(os.getenv("FISCAL_YEAR_START_MONTH", "4")),
    )
