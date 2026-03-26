"""仕訳CSV生成"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from acc_tool.csv_gen.rules import classify_account
from acc_tool.models import JournalEntry, OrderItem


def generate_journal_entries(items: list[OrderItem]) -> list[JournalEntry]:
    """注文データから仕訳エントリを生成

    貸方は全て「未払費用」で統一。
    借方科目はキーワードルールで推定。
    """
    entries: list[JournalEntry] = []
    for item in items:
        account, confidence = classify_account(item.product_name, item.amount)
        entries.append(
            JournalEntry(
                entry_date=item.order_date,
                debit_account=account,
                debit_amount=item.amount,
                credit_account="未払費用",
                credit_amount=item.amount,
                description=f"{item.vendor} {item.product_name}",
                confidence=confidence,
            )
        )
    return entries


def write_csv(
    entries: list[JournalEntry],
    output: Path | str | None = None,
    fmt: str = "generic",
) -> str:
    """仕訳CSVを出力

    Args:
        entries: 仕訳エントリ一覧
        output: 出力先パス (Noneならstdout文字列を返す)
        fmt: 出力形式 (generic / freee / yayoi / mf / zaimu_r4)

    Returns:
        CSV文字列
    """
    writer_func = _FORMAT_WRITERS.get(fmt, _write_generic)
    csv_text = writer_func(entries)

    if output:
        path = Path(output)
        encoding = "shift_jis" if fmt == "zaimu_r4" else "utf-8-sig"
        path.write_text(csv_text, encoding=encoding)

    return csv_text


def _write_generic(entries: list[JournalEntry]) -> str:
    """汎用CSV形式"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日付", "借方科目", "借方金額", "貸方科目", "貸方金額", "摘要"])
    for e in entries:
        w.writerow([
            e.entry_date.strftime("%Y/%m/%d"),
            e.debit_account,
            int(e.debit_amount),
            e.credit_account,
            int(e.credit_amount),
            e.description,
        ])
    return buf.getvalue()


def _write_freee(entries: list[JournalEntry]) -> str:
    """freee振替伝票インポート形式"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "取引日", "借方勘定科目", "借方金額(税込)",
        "貸方勘定科目", "貸方金額(税込)", "摘要",
    ])
    for e in entries:
        w.writerow([
            e.entry_date.strftime("%Y-%m-%d"),
            e.debit_account,
            int(e.debit_amount),
            e.credit_account,
            int(e.credit_amount),
            e.description,
        ])
    return buf.getvalue()


def _write_yayoi(entries: list[JournalEntry]) -> str:
    """弥生会計インポート形式"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "識別フラグ", "伝票No.", "決算", "取引日付", "借方勘定科目",
        "借方金額", "貸方勘定科目", "貸方金額", "摘要",
    ])
    for i, e in enumerate(entries, 1):
        w.writerow([
            2000,  # 仕訳データ
            i,
            "",
            e.entry_date.strftime("%Y/%m/%d"),
            e.debit_account,
            int(e.debit_amount),
            e.credit_account,
            int(e.credit_amount),
            e.description,
        ])
    return buf.getvalue()


def _write_mf(entries: list[JournalEntry]) -> str:
    """MFクラウド仕訳インポート形式"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "取引No", "取引日", "借方勘定科目", "借方金額",
        "貸方勘定科目", "貸方金額", "摘要",
    ])
    for i, e in enumerate(entries, 1):
        w.writerow([
            i,
            e.entry_date.strftime("%Y/%m/%d"),
            e.debit_account,
            int(e.debit_amount),
            e.credit_account,
            int(e.credit_amount),
            e.description,
        ])
    return buf.getvalue()


def _write_zaimu_r4(entries: list[JournalEntry]) -> str:
    """財務応援R4 仕訳データ取込形式 (Shift_JIS, 摘要48byte制限)"""
    buf = io.StringIO()
    w = csv.writer(buf)
    for e in entries:
        # 摘要を48byte(全角24文字)に切り詰め
        desc = _truncate_sjis(e.description, 48)
        w.writerow([
            e.entry_date.strftime("%Y/%m/%d"),
            e.debit_account,
            int(e.debit_amount),
            e.credit_account,
            int(e.credit_amount),
            desc,
        ])
    return buf.getvalue()


def _truncate_sjis(text: str, max_bytes: int) -> str:
    """Shift_JISでmax_bytesに収まるよう切り詰め"""
    result = ""
    byte_count = 0
    for ch in text:
        try:
            ch_bytes = len(ch.encode("shift_jis"))
        except UnicodeEncodeError:
            ch_bytes = 2  # エンコード不可は2byteとみなす
        if byte_count + ch_bytes > max_bytes:
            break
        result += ch
        byte_count += ch_bytes
    return result


_FORMAT_WRITERS = {
    "generic": _write_generic,
    "freee": _write_freee,
    "yayoi": _write_yayoi,
    "mf": _write_mf,
    "zaimu_r4": _write_zaimu_r4,
}
