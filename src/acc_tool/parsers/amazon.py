"""Amazon注文履歴HTMLパーサー

Amazon注文履歴ページのHTMLを解析して、注文データを抽出する。
対象ページ: https://www.amazon.co.jp/gp/your-account/order-history
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from acc_tool.models import OrderItem, ParseResult, Source


class _AmazonOrderParser(HTMLParser):
    """Amazon注文履歴HTMLの構造を解析するパーサー"""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[OrderItem] = []
        self.errors: list[str] = []

        # 状態管理
        self._in_order_card = False
        self._in_date = False
        self._in_total = False
        self._in_product = False
        self._in_order_id = False

        self._current_date: date | None = None
        self._current_total: Decimal | None = None
        self._current_products: list[str] = []
        self._current_order_id = ""
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""

        # 注文カードの検出 (order-card クラス)
        if "order-card" in cls or "order-info" in cls:
            # 前のカードのデータをフラッシュ
            self.flush_current()
            self._in_order_card = True
            self._current_products = []
            self._current_date = None
            self._current_total = None
            self._current_order_id = ""

        # 日付行
        if self._in_order_card and ("order-date" in cls or "a-color-secondary" in cls):
            self._in_date = True

        # 合計金額
        if self._in_order_card and ("a-color-price" in cls or "grand-total" in cls):
            self._in_total = True

        # 商品名リンク
        if self._in_order_card and tag == "a" and "yohtmlc-product-title" in cls:
            self._in_product = True

        # 注文番号
        if self._in_order_card and "order-id" in cls:
            self._in_order_id = True

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return

        if self._in_date:
            parsed = _parse_jp_date(text)
            if parsed:
                self._current_date = parsed
            self._in_date = False

        if self._in_total:
            amount = _parse_amount(text)
            if amount is not None:
                self._current_total = amount
            self._in_total = False

        if self._in_product:
            self._current_products.append(text)
            self._in_product = False

        if self._in_order_id:
            # "注文番号: 123-456-789" のパターン
            m = re.search(r"\d{3}-\d{7}-\d{7}", text)
            if m:
                self._current_order_id = m.group()
            self._in_order_id = False

    def handle_endtag(self, tag: str) -> None:
        # 注文カード終了は次のカード開始で暗黙的にリセット
        pass

    def flush_current(self) -> None:
        """現在バッファされている注文をitemsに追加"""
        if self._current_date and self._current_products:
            if len(self._current_products) == 1 and self._current_total:
                self.items.append(
                    OrderItem(
                        order_date=self._current_date,
                        vendor="Amazon",
                        product_name=self._current_products[0],
                        amount=self._current_total,
                        order_id=self._current_order_id,
                        source=Source.AMAZON,
                    )
                )
            elif self._current_products:
                # 複数商品の場合、合計を均等割（個別金額が取れない場合のフォールバック）
                per_item = (
                    self._current_total / len(self._current_products)
                    if self._current_total
                    else Decimal("0")
                )
                for name in self._current_products:
                    self.items.append(
                        OrderItem(
                            order_date=self._current_date,
                            vendor="Amazon",
                            product_name=name,
                            amount=per_item,
                            order_id=self._current_order_id,
                            source=Source.AMAZON,
                        )
                    )


def _parse_jp_date(text: str) -> date | None:
    """日本語日付文字列をパース: '2026年3月5日' or '2026/03/05'"""
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # "March 5, 2026" etc.
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(text: str) -> Decimal | None:
    """金額文字列をパース: '¥2,500', '￥2500', '2,500円' 等"""
    cleaned = re.sub(r"[¥￥円,\s]", "", text)
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_amazon_html(html: str) -> ParseResult:
    """Amazon注文履歴HTMLをパースして注文一覧を返す

    Args:
        html: Amazon注文履歴ページのHTML文字列

    Returns:
        ParseResult with extracted order items
    """
    parser = _AmazonOrderParser()
    try:
        parser.feed(html)
        parser.flush_current()
    except Exception as e:
        parser.errors.append(f"HTML解析エラー: {e}")

    # フォールバック: 構造化パースで取れなかった場合、正規表現ベースで抽出
    if not parser.items:
        items, errors = _regex_fallback(html)
        return ParseResult(items=items, errors=parser.errors + errors, source=Source.AMAZON)

    return ParseResult(items=parser.items, errors=parser.errors, source=Source.AMAZON)


def _regex_fallback(html: str) -> tuple[list[OrderItem], list[str]]:
    """HTMLタグ構造に依存しない正規表現フォールバック"""
    items: list[OrderItem] = []
    errors: list[str] = []

    # 注文日 + 合計 + 注文番号のブロックを探す
    blocks = re.split(r"(?=\d{4}年\s*\d{1,2}月\s*\d{1,2}日)", html)
    for block in blocks[1:]:  # 最初の空ブロックをスキップ
        d = _parse_jp_date(block[:30])
        if not d:
            continue

        amounts = re.findall(r"[¥￥]\s*([\d,]+)", block)
        # タイトル的なテキストを取得（<a>タグ内のテキスト等）
        titles = re.findall(r'title="([^"]+)"', block)
        if not titles:
            titles = re.findall(r">([^<]{5,80})</a>", block)

        if amounts and titles:
            total = _parse_amount(amounts[0]) or Decimal("0")
            for title in titles[:5]:  # 最大5商品
                items.append(
                    OrderItem(
                        order_date=d,
                        vendor="Amazon",
                        product_name=title.strip(),
                        amount=total if len(titles) == 1 else Decimal("0"),
                        source=Source.AMAZON,
                    )
                )

    if not items:
        errors.append("注文データを抽出できませんでした。HTMLの形式を確認してください。")

    return items, errors
