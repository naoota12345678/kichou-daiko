"""電帳法 事務処理規程の自動生成"""

from __future__ import annotations

from datetime import date
from pathlib import Path

REGULATION_TEMPLATE = """\
電子取引データの訂正及び削除の防止に関する事務処理規程

（目的）
第1条　本規程は、電子計算機を使用して作成する国税関係帳簿書類の保存方法等の
特例に関する法律第7条に規定された電子取引の取引情報に係る電磁的記録の保存に
ついて、適正かつ円滑な運用を確保するために必要な事項を定めることを目的とする。

（適用範囲）
第2条　本規程は、{company_name}（以下「当社」という。）における電子取引の
取引情報に係る電磁的記録の保存に適用する。

（管理責任者）
第3条　電子取引データの管理責任者は、代表者とする。

（電子取引の範囲）
第4条　当社における電子取引の範囲は以下のとおりとする。
一　ECサイト（Amazon、楽天市場等）での購入に係る領収書・注文確認メール
二　クレジットカード会社からの利用明細
三　電子メールにより受領する請求書・領収書
四　ウェブサイトからダウンロードする請求書・領収書

（取引データの保存）
第5条　電子取引データは、以下の方法により保存する。
一　保存場所：Google ドライブ（当社管理のアカウント）
二　保存期間：法定保存期間（7年間）
三　ファイル名：取引年月日_取引先_取引金額の形式とし、検索が可能な状態で保存する
四　保存形式：PDF、JPEG、PNG等の一般的なファイル形式

（訂正削除の原則禁止）
第6条　保存した電子取引データの訂正及び削除は、原則として禁止する。

（訂正削除が必要な場合）
第7条　やむを得ず訂正又は削除を行う場合は、以下の手続きに従う。
一　管理責任者の承認を得ること
二　訂正・削除の理由、日付、担当者を記録すること
三　訂正前のデータを別途保存すること

（検索機能の確保）
第8条　電子取引データは、以下の項目による検索ができる状態で保存する。
一　取引年月日
二　取引金額
三　取引先名称

附則
本規程は、{effective_date}から施行する。
"""


def generate_regulation(company_name: str, effective_date: date | None = None) -> str:
    """事務処理規程の本文を生成

    Args:
        company_name: 会社名・事業者名
        effective_date: 施行日 (デフォルトは今日)

    Returns:
        事務処理規程のテキスト
    """
    if effective_date is None:
        effective_date = date.today()

    return REGULATION_TEMPLATE.format(
        company_name=company_name,
        effective_date=effective_date.strftime("%Y年%m月%d日"),
    )


def save_regulation(
    company_name: str,
    output_dir: Path,
    effective_date: date | None = None,
) -> Path:
    """事務処理規程をファイルとして保存

    Args:
        company_name: 会社名
        output_dir: 出力先ディレクトリ
        effective_date: 施行日

    Returns:
        保存されたファイルのパス
    """
    text = generate_regulation(company_name, effective_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "電子取引データ保存に関する事務処理規程.txt"
    path.write_text(text, encoding="utf-8")

    return path
