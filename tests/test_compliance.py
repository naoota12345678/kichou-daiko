"""事務処理規程生成のテスト"""

from datetime import date
from pathlib import Path

from acc_tool.compliance.regulation import generate_regulation, save_regulation


class TestGenerateRegulation:
    def test_contains_company_name(self):
        text = generate_regulation("テスト株式会社")
        assert "テスト株式会社" in text

    def test_contains_date(self):
        text = generate_regulation("テスト株式会社", date(2026, 4, 1))
        assert "2026年04月01日" in text

    def test_contains_required_sections(self):
        text = generate_regulation("テスト株式会社")
        assert "訂正及び削除の防止" in text
        assert "検索機能の確保" in text
        assert "Google ドライブ" in text


class TestSaveRegulation:
    def test_creates_file(self, tmp_path: Path):
        path = save_regulation("テスト株式会社", tmp_path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "テスト株式会社" in content
