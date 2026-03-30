"""CSV出力 — 財務応援R4形式 + 汎用形式"""

from __future__ import annotations

import csv
import io
from models import JournalEntry


def export_zaimu_ouen(entries: list[JournalEntry]) -> str:
    """財務応援R4 仕訳インポート形式CSV（44列）Shift-JIS"""
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="cp932", errors="replace", newline="")

    writer = csv.writer(wrapper)

    writer.writerow([
        "月種別", "種類", "形式", "作成方法", "付箋",
        "伝票日付", "伝票番号", "伝票摘要", "枝番",
        "借方部門", "借方部門名",
        "借方科目", "借方科目名",
        "借方補助", "借方補助科目名",
        "借方金額",
        "借方消費税コード", "借方消費税業種", "借方消費税税率", "借方資金区分",
        "借方任意項目１", "借方任意項目２", "借方インボイス情報",
        "貸方部門", "貸方部門名",
        "貸方科目", "貸方科目名",
        "貸方補助", "貸方補助科目名",
        "貸方金額",
        "貸方消費税コード", "貸方消費税業種", "貸方消費税税率", "貸方資金区分",
        "貸方任意項目１", "貸方任意項目２", "貸方インボイス情報",
        "摘要", "期日", "証番号",
        "入力マシン", "入力ユーザ", "入力アプリ", "入力会社", "入力日付",
    ])

    for e in entries:
        # 日付をYYYYMMDD形式に変換（ハイフン除去）
        date_str = e.entry_date.replace("-", "") if e.entry_date else ""
        writer.writerow([
            "",  # 月種別
            "",  # 種類
            "",  # 形式
            "",  # 作成方法
            "",  # 付箋
            date_str,  # 伝票日付
            "",  # 伝票番号
            "",  # 伝票摘要
            "",  # 枝番
            "",  # 借方部門
            "",  # 借方部門名
            e.debit_code,  # 借方科目
            e.debit_account,  # 借方科目名
            e.debit_sub_code,  # 借方補助
            e.debit_sub_name,  # 借方補助科目名
            e.debit_amount,  # 借方金額
            e.debit_tax_category,  # 借方消費税コード
            "",  # 借方消費税業種
            e.tax_rate,  # 借方消費税税率
            "",  # 借方資金区分
            "",  # 借方任意項目１
            "",  # 借方任意項目２
            "",  # 借方インボイス情報
            "",  # 貸方部門
            "",  # 貸方部門名
            e.credit_code,  # 貸方科目
            e.credit_account,  # 貸方科目名
            e.credit_sub_code,  # 貸方補助
            e.credit_sub_name,  # 貸方補助科目名
            e.credit_amount,  # 貸方金額
            e.credit_tax_category,  # 貸方消費税コード
            "",  # 貸方消費税業種
            e.tax_rate,  # 貸方消費税税率
            "",  # 貸方資金区分
            "",  # 貸方任意項目１
            "",  # 貸方任意項目２
            "",  # 貸方インボイス情報
            e.description,  # 摘要
            "",  # 期日
            "",  # 証番号
            "",  # 入力マシン
            "",  # 入力ユーザ
            "",  # 入力アプリ
            "",  # 入力会社
            "",  # 入力日付
        ])

    wrapper.flush()
    return buf.getvalue()


def export_generic(entries: list[JournalEntry]) -> str:
    """汎用仕訳CSV（確認・デバッグ用）UTF-8 BOM"""
    output = io.StringIO()
    output.write("\ufeff")

    writer = csv.writer(output)
    writer.writerow([
        "日付", "借方科目", "借方コード", "借方補助", "借方補助名", "借方金額",
        "貸方科目", "貸方コード", "貸方補助", "貸方補助名", "貸方金額",
        "税率", "摘要", "取引先", "確信度", "判断根拠",
    ])

    for e in entries:
        writer.writerow([
            e.entry_date,
            e.debit_account,
            e.debit_code,
            e.debit_sub_code,
            e.debit_sub_name,
            e.debit_amount,
            e.credit_account,
            e.credit_code,
            e.credit_sub_code,
            e.credit_sub_name,
            e.credit_amount,
            f"{e.tax_rate}%",
            e.description,
            e.vendor,
            e.confidence,
            e.reasoning,
        ])

    return output.getvalue()
