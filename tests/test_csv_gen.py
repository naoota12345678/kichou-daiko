"""仕訳CSV生成のテスト"""

from datetime import date
from decimal import Decimal

from acc_tool.csv_gen.journal import generate_journal_entries, write_csv
from acc_tool.csv_gen.rules import classify_account
from acc_tool.models import OrderItem, Source


class TestClassifyAccount:
    def test_book(self):
        account, conf = classify_account("経営の教科書", Decimal("1200"))
        assert account == "新聞図書費"
        assert conf == "auto"

    def test_usb(self):
        account, _ = classify_account("USBハブ 4ポート", Decimal("2500"))
        assert account == "消耗品費"

    def test_ink(self):
        account, _ = classify_account("インクカートリッジ", Decimal("3000"))
        assert account == "消耗品費"

    def test_stationery(self):
        account, _ = classify_account("ボールペン 10本セット", Decimal("500"))
        assert account == "事務用品費"

    def test_unknown(self):
        account, conf = classify_account("よくわからない商品", Decimal("5000"))
        assert "不明" in account
        assert conf == "unknown"

    def test_high_amount(self):
        account, conf = classify_account("パソコン", Decimal("150000"))
        assert "要確認" in account
        assert conf == "unknown"

    def test_coffee(self):
        account, _ = classify_account("コーヒー豆 500g", Decimal("800"))
        assert account == "会議費"


class TestJournalEntries:
    def test_basic(self):
        items = [
            OrderItem(
                order_date=date(2026, 3, 5),
                vendor="Amazon",
                product_name="コピー用紙A4",
                amount=Decimal("3980"),
                source=Source.AMAZON,
            ),
        ]
        entries = generate_journal_entries(items)
        assert len(entries) == 1
        assert entries[0].debit_account == "消耗品費"
        assert entries[0].credit_account == "未払費用"
        assert entries[0].debit_amount == Decimal("3980")
        assert "Amazon" in entries[0].description


class TestWriteCsv:
    def test_generic_format(self):
        items = [
            OrderItem(
                order_date=date(2026, 3, 5),
                vendor="Amazon",
                product_name="USBハブ",
                amount=Decimal("2500"),
            ),
        ]
        entries = generate_journal_entries(items)
        csv_text = write_csv(entries, fmt="generic")
        assert "日付" in csv_text
        assert "2026/03/05" in csv_text
        assert "消耗品費" in csv_text
        assert "2500" in csv_text

    def test_freee_format(self):
        items = [
            OrderItem(
                order_date=date(2026, 3, 5),
                vendor="Amazon",
                product_name="本",
                amount=Decimal("1200"),
            ),
        ]
        entries = generate_journal_entries(items)
        csv_text = write_csv(entries, fmt="freee")
        assert "取引日" in csv_text
        assert "2026-03-05" in csv_text

    def test_zaimu_r4_truncation(self):
        items = [
            OrderItem(
                order_date=date(2026, 3, 5),
                vendor="Amazon",
                product_name="とても長い商品名が入っている場合にちゃんと切り詰められるかテスト",
                amount=Decimal("1000"),
            ),
        ]
        entries = generate_journal_entries(items)
        csv_text = write_csv(entries, fmt="zaimu_r4")
        # 各行の摘要が48byteに収まっていること
        for line in csv_text.strip().split("\n"):
            parts = line.split(",")
            if len(parts) >= 6:
                desc = parts[5]
                assert len(desc.encode("shift_jis", errors="replace")) <= 48
