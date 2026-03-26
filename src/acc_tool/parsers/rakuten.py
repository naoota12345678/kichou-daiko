"""楽天注文履歴HTMLパーサー

楽天注文履歴ページのHTMLを解析して、注文データを抽出する。
対象ページ: https://order.my.rakuten.co.jp/
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from acc_tool.models import OrderItem, ParseResult, Source


def parse_rakuten_html(html: str) -> ParseResult:
    """楽天注文履歴HTMLをパースして注文一覧を返す"""
    items: list[OrderItem] = []
    errors: list[str] = []

    try:
        items = _extract_orders(html)
    except Exception as e:
        errors.append(f"楽天HTML解析エラー: {e}")

    if not items and not errors:
        errors.append("注文データを抽出できませんでした。HTMLの形式を確認してください。")

    return ParseResult(items=items, errors=errors, source=Source.RAKUTEN)


def _extract_orders(html: str) -> list[OrderItem]:
    """楽天注文履歴からデータ抽出

    楽天の注文履歴は以下のような構造:
    - 注文日: "2026/03/05" or "2026年03月05日"
    - 店舗名: ショップ名
    - 商品名: 商品タイトル
    - 金額: "¥2,500" or "2,500円"
    - 注文番号
    """
    items: list[OrderItem] = []

    # ブロック分割: 注文ごとのセクション
    # 楽天は "注文日時" や日付でブロックが分かれる
    order_blocks = re.split(r"(?=注文日時[：:]\s*\d{4})", html)
    if len(order_blocks) <= 1:
        # 別フォーマット: 日付パターンで分割
        order_blocks = re.split(r"(?=\d{4}[/年]\d{1,2}[/月]\d{1,2}[日]?)", html)

    for block in order_blocks[1:]:
        order_date = _parse_date(block[:50])
        if not order_date:
            continue

        # 店舗名
        shop = _extract_shop(block)

        # 商品名と金額のペアを抽出
        product_amounts = _extract_product_amounts(block)

        if product_amounts:
            for name, amount in product_amounts:
                items.append(
                    OrderItem(
                        order_date=order_date,
                        vendor=shop or "楽天",
                        product_name=name,
                        amount=amount,
                        source=Source.RAKUTEN,
                    )
                )
        else:
            # 商品名だけ or 合計だけ取れた場合
            names = _extract_product_names(block)
            total = _extract_total(block)
            for name in names:
                items.append(
                    OrderItem(
                        order_date=order_date,
                        vendor=shop or "楽天",
                        product_name=name,
                        amount=total / len(names) if total and names else Decimal("0"),
                        source=Source.RAKUTEN,
                    )
                )

    return items


def _parse_date(text: str) -> date | None:
    """日付文字列をパース"""
    m = re.search(r"(\d{4})\s*[/年]\s*(\d{1,2})\s*[/月]\s*(\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_shop(block: str) -> str:
    """店舗名を抽出"""
    # "ショップ名: XXX" パターン
    m = re.search(r"(?:ショップ|店舗)[名：:]\s*([^\n<]+)", block)
    if m:
        return m.group(1).strip()
    # ショップリンクから
    m = re.search(r'shop\.rakuten\.co\.jp/([^/"]+)', block)
    if m:
        return m.group(1)
    return ""


def _extract_product_amounts(block: str) -> list[tuple[str, Decimal]]:
    """商品名と金額のペアを抽出"""
    results: list[tuple[str, Decimal]] = []

    # 商品名の後に金額が続くパターン
    # <td>商品名</td>...<td>¥1,234</td> 的な構造
    rows = re.findall(
        r"(?:商品名[：:]?\s*|item[_-]name[^>]*>)\s*([^<\n]{3,80})\s*.*?"
        r"[¥￥]\s*([\d,]+)",
        block,
        re.DOTALL,
    )
    for name, amt_str in rows:
        try:
            amount = Decimal(amt_str.replace(",", ""))
            results.append((name.strip(), amount))
        except InvalidOperation:
            continue

    return results


def _extract_product_names(block: str) -> list[str]:
    """商品名を抽出"""
    names: list[str] = []
    # タイトル属性から
    titles = re.findall(r'title="([^"]{3,100})"', block)
    if titles:
        return [t.strip() for t in titles[:10]]
    # リンクテキストから
    links = re.findall(r">([^<]{5,100})</a>", block)
    return [ln.strip() for ln in links[:10] if not re.match(r"^[\d\s/年月日]+$", ln)]


def _extract_total(block: str) -> Decimal | None:
    """合計金額を抽出"""
    # "合計" の近くの金額
    m = re.search(r"合計[^¥￥\d]*[¥￥]\s*([\d,]+)", block)
    if m:
        try:
            return Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            pass
    # 最初に見つかった金額
    m = re.search(r"[¥￥]\s*([\d,]+)", block)
    if m:
        try:
            return Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            pass
    return None
