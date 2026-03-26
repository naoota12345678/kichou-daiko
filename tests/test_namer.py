"""ファイル名生成のテスト"""

from datetime import date
from decimal import Decimal

from acc_tool.drive.namer import generate_filename, generate_folder_path, generate_receipt_filename
from acc_tool.models import OrderItem


class TestGenerateFilename:
    def test_basic(self):
        item = OrderItem(
            order_date=date(2026, 3, 5),
            vendor="Amazon",
            product_name="コピー用紙A4",
            amount=Decimal("3980"),
        )
        assert generate_filename(item) == "20260305_Amazon_コピー用紙A4_3980.pdf"

    def test_with_invoice(self):
        item = OrderItem(
            order_date=date(2026, 3, 5),
            vendor="Amazon",
            product_name="USBハブ",
            amount=Decimal("2500"),
            invoice_number="T1234567890123",
        )
        name = generate_filename(item)
        assert name == "20260305_Amazon_USBハブ_2500_T1234567890123.pdf"

    def test_long_product_name_truncated(self):
        item = OrderItem(
            order_date=date(2026, 3, 5),
            vendor="Amazon",
            product_name="A" * 50,
            amount=Decimal("1000"),
        )
        name = generate_filename(item)
        # 品名は30文字に切り詰め
        parts = name.replace(".pdf", "").split("_")
        assert len(parts[2]) <= 30

    def test_special_chars_removed(self):
        item = OrderItem(
            order_date=date(2026, 3, 5),
            vendor="Amazon",
            product_name='テスト"品<名>',
            amount=Decimal("500"),
        )
        name = generate_filename(item)
        assert '"' not in name
        assert "<" not in name

    def test_jpg_extension(self):
        item = OrderItem(
            order_date=date(2026, 3, 5),
            vendor="セブンイレブン",
            product_name="コーヒー",
            amount=Decimal("150"),
        )
        assert generate_filename(item, ext=".jpg").endswith(".jpg")


class TestReceiptFilename:
    def test_basic(self):
        assert generate_receipt_filename(1, "20260310") == "20260310_レシート_001.jpg"

    def test_seq_padding(self):
        assert generate_receipt_filename(42, "20260310") == "20260310_レシート_042.jpg"


class TestFolderPath:
    def test_april_start(self):
        # 4月始まり、6月 → 2025年度
        assert generate_folder_path(4, 2025, 6) == "2025年度/06月/領収書"

    def test_april_start_march(self):
        # 4月始まり、3月 → 前年度
        assert generate_folder_path(4, 2026, 3) == "2025年度/03月/領収書"

    def test_jan_start(self):
        # 1月始まり、12月 → 当年度
        assert generate_folder_path(1, 2025, 12) == "2025年度/12月/領収書"
