"""CSV出力 — 財務応援R4形式 + 汎用形式"""

from __future__ import annotations

import csv
import io
from models import JournalEntry


def export_zaimu_ouen(entries: list[JournalEntry]) -> str:
    """財務応援R4 仕訳インポート形式CSV"""
    output = io.StringIO()
    output.write("\ufeff")

    writer = csv.writer(output)

    writer.writerow([
        "日付",
        "借方科目コード",
        "借方科目名",
        "借方金額",
        "借方税区分",
        "貸方科目コード",
        "貸方科目名",
        "貸方金額",
        "貸方税区分",
        "摘要",
        "税率",
        "取引先",
    ])

    for e in entries:
        writer.writerow([
            e.entry_date,
            e.debit_code,
            e.debit_account,
            e.debit_amount,
            e.debit_tax_category,
            e.credit_code,
            e.credit_account,
            e.credit_amount,
            e.credit_tax_category,
            e.description,
            f"{e.tax_rate}%",
            e.vendor,
        ])

    return output.getvalue()


def export_generic(entries: list[JournalEntry]) -> str:
    """汎用仕訳CSV（確認・デバッグ用）"""
    output = io.StringIO()
    output.write("\ufeff")

    writer = csv.writer(output)
    writer.writerow([
        "日付", "借方科目", "借方金額", "貸方科目", "貸方金額",
        "税率", "摘要", "取引先", "確信度", "判断根拠",
    ])

    for e in entries:
        writer.writerow([
            e.entry_date,
            e.debit_account,
            e.debit_amount,
            e.credit_account,
            e.credit_amount,
            f"{e.tax_rate}%",
            e.description,
            e.vendor,
            e.confidence,
            e.reasoning,
        ])

    return output.getvalue()
