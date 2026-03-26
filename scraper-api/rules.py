"""科目推定ルール（キーワードマッチング）"""

from __future__ import annotations

import re
from decimal import Decimal

# (パターン正規表現, 科目名) の優先順リスト
KEYWORD_RULES: list[tuple[str, str]] = [
    # 事務用品（書籍より先に判定: 「ペン」が「10本」にマッチしないように）
    (r"文房具|ボールペン|万年筆|シャーペン|ノート[^パPC]|ファイル|封筒|クリップ|ホッチキス|付箋|テープ|修正液", "事務用品費"),
    # 書籍・図書（「本」は単独出現のみ: 「10本」等を除外）
    (r"書籍|教科書|ブック|図書|雑誌|新聞|kindle|(?<!\d)本(?!セット|入|組|パック|束)", "新聞図書費"),
    # 消耗品（IT系）
    (r"USB|ケーブル|マウス|キーボード|充電|アダプタ|ハブ|SSD|HDD|メモリ|SDカード", "消耗品費"),
    # 消耗品（印刷系）
    (r"インク|トナー|用紙|コピー|プリンタ|印刷", "消耗品費"),
    # 消耗品（一般）
    (r"電池|電球|洗剤|ゴミ袋|スポンジ|ラップ|ティッシュ|タオル", "消耗品費"),
    # 通信費
    (r"通信|電話|携帯|SIM|Wi-?Fi|インターネット|プロバイダ|ドメイン|サーバー", "通信費"),
    # ソフトウェア・サブスク
    (r"ソフト|ライセンス|サブスク|月額|年額|Microsoft|Adobe|Google|AWS", "通信費"),
    # 交通費
    (r"新幹線|電車|バス|タクシー|航空|飛行機|ETC|ガソリン|駐車", "旅費交通費"),
    # 宿泊
    (r"ホテル|旅館|宿泊|inn|hotel", "旅費交通費"),
    # 飲食（会議費）
    (r"コーヒー|カフェ|お茶|ドリンク|サンドイッチ|弁当|ランチ", "会議費"),
    # 荷造運賃
    (r"送料|運賃|宅配|郵便|切手|レターパック|ゆうパック|ヤマト|佐川", "荷造運賃"),
    # 修繕費
    (r"修理|修繕|メンテナンス|交換|整備", "修繕費"),
    # 広告宣伝
    (r"広告|宣伝|チラシ|名刺|看板|Web広告|Google広告|Facebook広告", "広告宣伝費"),
    # 保険
    (r"保険|保険料", "保険料"),
]


def classify_account(product_name: str, amount: Decimal) -> tuple[str, str]:
    """商品名と金額から勘定科目を推定

    Args:
        product_name: 商品名
        amount: 金額

    Returns:
        (科目名, 確信度): 確信度は "auto" or "unknown"
    """
    # 10万円以上は要確認
    if amount >= 100_000:
        return "【要確認: 資産計上の可能性】消耗品費", "unknown"

    name_lower = product_name.lower()

    for pattern, account in KEYWORD_RULES:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return account, "auto"

    return "【不明】", "unknown"
