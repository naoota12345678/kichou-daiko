"""重複チェック"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from models import OrderItem


@dataclass
class DuplicateMatch:
    """重複検出結果"""

    existing_filename: str
    match_type: str  # exact / date_amount / similar
    confidence: float  # 0.0 - 1.0


def check_duplicate(item: OrderItem, existing_files: list[str]) -> DuplicateMatch | None:
    """既存ファイル名一覧と照合して重複を検出

    重複判定:
    - 日付 × 金額 × 取引先 が一致 → exact (1.0)
    - 日付(±1日) × 金額 が一致 → date_amount (0.8)
    - 日付(±3日) × 金額 × 類似取引先 → similar (0.6)

    Args:
        item: チェック対象の注文データ
        existing_files: 既存ファイル名リスト

    Returns:
        DuplicateMatch or None
    """
    item_date_str = item.order_date.strftime("%Y%m%d")
    item_amount = str(item.amount_int)
    item_vendor = item.vendor

    for fname in existing_files:
        parts = _parse_filename(fname)
        if not parts:
            continue

        f_date, f_vendor, f_amount = parts

        # exact: 日付 + 金額 + 取引先 完全一致
        if f_date == item_date_str and f_amount == item_amount and f_vendor == item_vendor:
            return DuplicateMatch(
                existing_filename=fname, match_type="exact", confidence=1.0
            )

        # date_amount: 日付±1日 + 金額一致
        if f_amount == item_amount and _date_within(item_date_str, f_date, days=1):
            return DuplicateMatch(
                existing_filename=fname, match_type="date_amount", confidence=0.8
            )

        # similar: 日付±3日 + 金額一致
        if f_amount == item_amount and _date_within(item_date_str, f_date, days=3):
            return DuplicateMatch(
                existing_filename=fname, match_type="similar", confidence=0.6
            )

    return None


def _parse_filename(fname: str) -> tuple[str, str, str] | None:
    """電帳法ファイル名から日付・取引先・金額を抽出

    形式: YYYYMMDD_取引先_品名_金額[_インボイス番号].ext
    """
    stem = Path(fname).stem
    parts = stem.split("_")
    if len(parts) < 4:
        return None

    f_date = parts[0]
    if not re.match(r"\d{8}$", f_date):
        return None

    f_vendor = parts[1]
    # 金額は末尾側（インボイス番号がある場合は末尾から2番目）
    f_amount = ""
    for p in reversed(parts[2:]):
        if re.match(r"^T\d{13}$", p):
            continue
        if re.match(r"^\d+$", p):
            f_amount = p
            break

    if not f_amount:
        return None

    return f_date, f_vendor, f_amount


def _date_within(date1_str: str, date2_str: str, days: int) -> bool:
    """2つの日付文字列(YYYYMMDD)が指定日数以内か"""
    try:
        d1 = date(int(date1_str[:4]), int(date1_str[4:6]), int(date1_str[6:8]))
        d2 = date(int(date2_str[:4]), int(date2_str[4:6]), int(date2_str[6:8]))
        return abs((d1 - d2).days) <= days
    except (ValueError, IndexError):
        return False
