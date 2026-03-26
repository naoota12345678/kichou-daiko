"""電帳法準拠ファイル名生成"""

from __future__ import annotations

import re
import unicodedata

from acc_tool.models import OrderItem


def generate_filename(item: OrderItem, ext: str = ".pdf") -> str:
    """電帳法準拠のファイル名を生成

    形式: {YYYYMMDD}_{取引先}_{品名}_{金額}_{インボイス番号}.ext
    例: 20260305_Amazon_コピー用紙A4_3980_T1234567890123.pdf

    Args:
        item: 注文データ
        ext: 拡張子 (デフォルト .pdf)

    Returns:
        ファイル名文字列
    """
    parts = [
        item.order_date.strftime("%Y%m%d"),
        _sanitize(item.vendor),
        _truncate(_sanitize(item.product_name), max_len=30),
        str(item.amount_int),
    ]

    if item.invoice_number:
        parts.append(item.invoice_number)

    filename = "_".join(parts) + ext
    return filename


def generate_receipt_filename(seq: int, capture_date_str: str, ext: str = ".jpg") -> str:
    """レシート撮影画像のファイル名を生成

    形式: {YYYYMMDD}_レシート_{連番}.ext
    例: 20260310_レシート_001.jpg
    """
    return f"{capture_date_str}_レシート_{seq:03d}{ext}"


def generate_folder_path(fiscal_year_start_month: int, year: int, month: int) -> str:
    """年度/月のフォルダパスを生成

    Args:
        fiscal_year_start_month: 会計年度の開始月 (4=4月始まり)
        year: 年
        month: 月

    Returns:
        例: "2025年度/04月/領収書"
    """
    # 会計年度を計算
    if month < fiscal_year_start_month:
        fiscal_year = year - 1
    else:
        fiscal_year = year

    return f"{fiscal_year}年度/{month:02d}月/領収書"


def _sanitize(text: str) -> str:
    """ファイル名に使えない文字を除去"""
    # NFKC正規化（全角→半角など）
    text = unicodedata.normalize("NFKC", text)
    # ファイル名に使えない文字を除去
    text = re.sub(r'[\\/:*?"<>|\n\r\t]', "", text)
    # 連続スペースを1つに
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text: str, max_len: int = 30) -> str:
    """長すぎるテキストを切り詰め"""
    if len(text) <= max_len:
        return text
    return text[:max_len]
