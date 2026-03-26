"""パーサーのテスト"""

from datetime import date
from decimal import Decimal

from acc_tool.parsers.amazon import parse_amazon_html, _parse_jp_date, _parse_amount
from acc_tool.parsers.rakuten import parse_rakuten_html


class TestAmazonDateParsing:
    def test_jp_date(self):
        assert _parse_jp_date("2026年3月5日") == date(2026, 3, 5)

    def test_jp_date_with_spaces(self):
        assert _parse_jp_date("2026 年 3 月 5 日") == date(2026, 3, 5)

    def test_slash_date(self):
        assert _parse_jp_date("2026/03/05") == date(2026, 3, 5)

    def test_hyphen_date(self):
        assert _parse_jp_date("2026-03-05") == date(2026, 3, 5)

    def test_invalid_returns_none(self):
        assert _parse_jp_date("abc") is None


class TestAmazonAmountParsing:
    def test_yen_comma(self):
        assert _parse_amount("¥2,500") == Decimal("2500")

    def test_fullwidth_yen(self):
        assert _parse_amount("￥12,500") == Decimal("12500")

    def test_en_suffix(self):
        assert _parse_amount("2,500円") == Decimal("2500")

    def test_no_comma(self):
        assert _parse_amount("¥500") == Decimal("500")

    def test_invalid_returns_none(self):
        assert _parse_amount("abc") is None


class TestAmazonParser:
    SAMPLE_HTML = """
    <div class="order-card">
        <span class="order-date">2026年3月5日</span>
        <span class="a-color-price">¥3,980</span>
        <a class="yohtmlc-product-title">コピー用紙A4 500枚</a>
        <span class="order-id">注文番号: 250-1234567-7654321</span>
    </div>
    <div class="order-card">
        <span class="order-date">2026年3月8日</span>
        <span class="a-color-price">¥2,500</span>
        <a class="yohtmlc-product-title">USBハブ 4ポート</a>
    </div>
    """

    def test_parse_items(self):
        result = parse_amazon_html(self.SAMPLE_HTML)
        assert len(result.items) == 2
        assert result.items[0].product_name == "コピー用紙A4 500枚"
        assert result.items[0].amount == Decimal("3980")
        assert result.items[0].order_date == date(2026, 3, 5)

    def test_parse_vendor(self):
        result = parse_amazon_html(self.SAMPLE_HTML)
        assert result.items[0].vendor == "Amazon"

    def test_parse_order_id(self):
        result = parse_amazon_html(self.SAMPLE_HTML)
        assert result.items[0].order_id == "250-1234567-7654321"

    def test_empty_html(self):
        result = parse_amazon_html("<html><body></body></html>")
        assert len(result.items) == 0
        assert len(result.errors) > 0

    def test_regex_fallback(self):
        html = """
        2026年3月10日 に注文
        <a title="エルゴノミクスマウス">リンク</a>
        ¥4,500
        """
        result = parse_amazon_html(html)
        assert len(result.items) >= 1


class TestRakutenParser:
    SAMPLE_HTML = """
    注文日時: 2026/03/05 12:30
    ショップ名: テスト楽天ショップ
    <a title="ワイヤレスイヤホン Bluetooth">商品リンク</a>
    合計 ¥5,980
    注文日時: 2026/03/10 15:00
    ショップ名: 文房具ストア
    <a title="ボールペン 10本セット">商品リンク</a>
    合計 ¥1,200
    """

    def test_parse_items(self):
        result = parse_rakuten_html(self.SAMPLE_HTML)
        assert len(result.items) >= 1

    def test_empty_html(self):
        result = parse_rakuten_html("<html></html>")
        assert len(result.items) == 0
        assert len(result.errors) > 0
