"""重複チェックのテスト"""

from datetime import date
from decimal import Decimal

from acc_tool.drive.dedup import check_duplicate, _parse_filename
from acc_tool.models import OrderItem


class TestParseFilename:
    def test_basic(self):
        result = _parse_filename("20260305_Amazon_コピー用紙A4_3980.pdf")
        assert result == ("20260305", "Amazon", "3980")

    def test_with_invoice(self):
        result = _parse_filename("20260305_Amazon_USBハブ_2500_T1234567890123.pdf")
        assert result == ("20260305", "Amazon", "2500")

    def test_invalid(self):
        assert _parse_filename("readme.txt") is None


class TestCheckDuplicate:
    EXISTING = [
        "20260305_Amazon_コピー用紙A4_3980.pdf",
        "20260308_Amazon_USBハブ_2500.pdf",
        "20260310_セブンイレブン_コーヒー_150.jpg",
    ]

    def test_exact_match(self):
        item = OrderItem(
            order_date=date(2026, 3, 5),
            vendor="Amazon",
            product_name="コピー用紙A4",
            amount=Decimal("3980"),
        )
        match = check_duplicate(item, self.EXISTING)
        assert match is not None
        assert match.match_type == "exact"
        assert match.confidence == 1.0

    def test_date_amount_match(self):
        item = OrderItem(
            order_date=date(2026, 3, 6),  # 1日ずれ
            vendor="楽天",
            product_name="用紙",
            amount=Decimal("3980"),  # 同額
        )
        match = check_duplicate(item, self.EXISTING)
        assert match is not None
        assert match.match_type == "date_amount"

    def test_no_match(self):
        item = OrderItem(
            order_date=date(2026, 3, 20),
            vendor="ヨドバシ",
            product_name="テレビ",
            amount=Decimal("50000"),
        )
        match = check_duplicate(item, self.EXISTING)
        assert match is None
