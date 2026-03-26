"""CLI エントリーポイント"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="acc-tool: 経理半自動化CLIツール")


@app.command()
def version():
    """バージョン表示"""
    from acc_tool import __version__

    typer.echo(f"acc-tool v{__version__}")


@app.command()
def status():
    """現在の設定状況を表示"""
    from acc_tool.config import settings

    cfg = settings.load()
    typer.echo(f"会計年度開始月: {cfg.fiscal_year_start_month}月")
    typer.echo(f"Googleドライブ: {'設定済み' if cfg.drive_folder_id else '未設定'}")


@app.command()
def fetch_amazon(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="対象年 (例: 2025)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="CSV出力先"),
    fmt: str = typer.Option("generic", "--format", "-f", help="CSV形式"),
    receipts: Optional[Path] = typer.Option(None, "--receipts", "-r", help="領収書PDFの保存先ディレクトリ"),
    save_html: Optional[Path] = typer.Option(None, "--save-html", help="HTMLを保存するディレクトリ"),
):
    """Amazon注文を自動取得 => 仕訳CSV生成 + 領収書PDF保存（電帳法対応）"""
    from acc_tool.csv_gen.journal import generate_journal_entries, write_csv
    from acc_tool.scrapers.amazon_scraper import scrape_amazon

    result = scrape_amazon(year=year, save_html_dir=save_html)

    if result.errors:
        for err in result.errors:
            typer.echo(f"[!] {err}", err=True)

    if not result.items:
        typer.echo("No orders found.")
        raise typer.Exit(1)

    typer.echo(f"\n[OK] {len(result.items)} orders found")
    for item in result.items:
        typer.echo(f"  {item.order_date} {item.vendor} {item.product_name} {item.amount_int:,}")

    # 仕訳CSV
    entries = generate_journal_entries(result.items)
    csv_text = write_csv(entries, output=output, fmt=fmt)

    if output:
        typer.echo(f"\n[OK] CSV: {output}")
    else:
        typer.echo("\n--- CSV ---")
        typer.echo(csv_text)

    # 領収書PDFダウンロード
    if receipts:
        from acc_tool.config import settings
        from acc_tool.scrapers.amazon_receipt import download_receipts

        cfg = settings.load()
        typer.echo(f"\nDownloading receipts to {receipts}/ ...")
        download_receipts(
            result.items,
            output_dir=receipts,
            fiscal_year_start_month=cfg.fiscal_year_start_month,
        )
    else:
        typer.echo("\n--- CSV ---")
        typer.echo(csv_text)


@app.command()
def fetch_rakuten(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="対象年 (例: 2025)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="CSV出力先"),
    fmt: str = typer.Option("generic", "--format", "-f", help="CSV形式"),
    receipts: Optional[Path] = typer.Option(None, "--receipts", "-r", help="領収書PDFの保存先"),
):
    """楽天注文を自動取得 => 仕訳CSV生成 + 領収書PDF保存"""
    from acc_tool.csv_gen.journal import generate_journal_entries, write_csv
    from acc_tool.scrapers.rakuten_scraper import scrape_rakuten

    result = scrape_rakuten(year=year)

    if result.errors:
        for err in result.errors:
            typer.echo(f"[!] {err}", err=True)

    if not result.items:
        typer.echo("No orders found.")
        raise typer.Exit(1)

    typer.echo(f"\n[OK] {len(result.items)} orders found")
    for item in result.items:
        typer.echo(f"  {item.order_date} {item.vendor} {item.product_name} {item.amount_int:,}")

    entries = generate_journal_entries(result.items)
    csv_text = write_csv(entries, output=output, fmt=fmt)

    if output:
        typer.echo(f"\n[OK] CSV: {output}")

    if receipts:
        from acc_tool.config import settings
        from acc_tool.scrapers.rakuten_receipt import download_receipts

        cfg = settings.load()
        typer.echo(f"\nDownloading receipts to {receipts}/ ...")
        download_receipts(
            result.items,
            output_dir=receipts,
            fiscal_year_start_month=cfg.fiscal_year_start_month,
        )
    elif not output:
        typer.echo("\n--- CSV ---")
        typer.echo(csv_text)


@app.command()
def fetch_yahoo(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="対象年 (例: 2025)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="CSV出力先"),
    fmt: str = typer.Option("generic", "--format", "-f", help="CSV形式"),
    receipts: Optional[Path] = typer.Option(None, "--receipts", "-r", help="領収書PDFの保存先"),
):
    """Yahooショッピング注文を自動取得 => 仕訳CSV生成 + 領収書PDF保存"""
    from acc_tool.csv_gen.journal import generate_journal_entries, write_csv
    from acc_tool.scrapers.yahoo_scraper import scrape_yahoo

    result = scrape_yahoo(year=year)

    if result.errors:
        for err in result.errors:
            typer.echo(f"[!] {err}", err=True)

    if not result.items:
        typer.echo("No orders found.")
        raise typer.Exit(1)

    typer.echo(f"\n[OK] {len(result.items)} orders found")
    for item in result.items:
        typer.echo(f"  {item.order_date} {item.vendor} {item.product_name} {item.amount_int:,}")

    entries = generate_journal_entries(result.items)
    csv_text = write_csv(entries, output=output, fmt=fmt)

    if output:
        typer.echo(f"\n[OK] CSV: {output}")

    if receipts:
        from acc_tool.config import settings
        from acc_tool.scrapers.yahoo_receipt import download_receipts

        cfg = settings.load()
        typer.echo(f"\nDownloading receipts to {receipts}/ ...")
        download_receipts(
            result.items,
            output_dir=receipts,
            fiscal_year_start_month=cfg.fiscal_year_start_month,
        )
    elif not output:
        typer.echo("\n--- CSV ---")
        typer.echo(csv_text)


@app.command()
def parse_amazon(
    html_file: Path = typer.Argument(..., help="Amazon注文履歴HTMLファイル"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="CSV出力先"),
    fmt: str = typer.Option("generic", "--format", "-f", help="CSV形式 (generic/freee/yayoi/mf/zaimu_r4)"),
):
    """Amazon注文履歴HTMLを解析して仕訳CSVを生成"""
    from acc_tool.csv_gen.journal import generate_journal_entries, write_csv
    from acc_tool.parsers.amazon import parse_amazon_html

    html = html_file.read_text(encoding="utf-8")
    result = parse_amazon_html(html)

    if result.errors:
        for err in result.errors:
            typer.echo(f"[!] {err}", err=True)

    if not result.items:
        typer.echo("注文データが見つかりませんでした。")
        raise typer.Exit(1)

    typer.echo(f"[OK] {len(result.items)}件の注文を検出")

    for item in result.items:
        typer.echo(f"  {item.order_date} {item.vendor} {item.product_name} {item.amount_int:,}")

    entries = generate_journal_entries(result.items)
    csv_text = write_csv(entries, output=output, fmt=fmt)

    if output:
        typer.echo(f"[OK] CSV出力: {output}")
    else:
        typer.echo("\n--- 仕訳CSV ---")
        typer.echo(csv_text)


@app.command()
def parse_rakuten(
    html_file: Path = typer.Argument(..., help="楽天注文履歴HTMLファイル"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="CSV出力先"),
    fmt: str = typer.Option("generic", "--format", "-f", help="CSV形式"),
):
    """楽天注文履歴HTMLを解析して仕訳CSVを生成"""
    from acc_tool.csv_gen.journal import generate_journal_entries, write_csv
    from acc_tool.parsers.rakuten import parse_rakuten_html

    html = html_file.read_text(encoding="utf-8")
    result = parse_rakuten_html(html)

    if result.errors:
        for err in result.errors:
            typer.echo(f"[!] {err}", err=True)

    if not result.items:
        typer.echo("注文データが見つかりませんでした。")
        raise typer.Exit(1)

    typer.echo(f"[OK] {len(result.items)}件の注文を検出")

    for item in result.items:
        typer.echo(f"  {item.order_date} {item.vendor} {item.product_name} {item.amount_int:,}")

    entries = generate_journal_entries(result.items)
    csv_text = write_csv(entries, output=output, fmt=fmt)

    if output:
        typer.echo(f"[OK] CSV出力: {output}")
    else:
        typer.echo("\n--- 仕訳CSV ---")
        typer.echo(csv_text)


@app.command()
def gen_regulation(
    company_name: str = typer.Argument(..., help="会社名・事業者名"),
    output_dir: Path = typer.Option(".", "--output", "-o", help="出力先ディレクトリ"),
):
    """電帳法 事務処理規程を自動生成"""
    from acc_tool.compliance.regulation import save_regulation

    path = save_regulation(company_name, output_dir)
    typer.echo(f"[OK] 事務処理規程を生成: {path}")


@app.command()
def upload(
    files: list[Path] = typer.Argument(..., help="アップロードするファイル"),
    folder_id: Optional[str] = typer.Option(None, "--folder", help="Googleドライブフォルダ ID"),
):
    """ファイルをGoogleドライブにアップロード"""
    from acc_tool.config import settings
    from acc_tool.drive.uploader import authenticate, upload_file

    cfg = settings.load()
    target_folder = folder_id or cfg.drive_folder_id

    if not target_folder:
        typer.echo("エラー: Googleドライブフォルダが未設定です。")
        typer.echo("GOOGLE_DRIVE_FOLDER_ID を .env に設定するか --folder で指定してください。")
        raise typer.Exit(1)

    creds = authenticate()

    for f in files:
        if not f.exists():
            typer.echo(f"[!] ファイルが見つかりません: {f}", err=True)
            continue

        file_id = upload_file(f, f.name, target_folder, creds)
        typer.echo(f"[OK] アップロード完了: {f.name} (ID: {file_id})")


@app.command()
def rename(
    files: list[Path] = typer.Argument(..., help="リネーム対象ファイル"),
    vendor: str = typer.Option("", "--vendor", "-v", help="取引先名"),
    product: str = typer.Option("", "--product", "-p", help="品名"),
    amount: int = typer.Option(0, "--amount", "-a", help="金額"),
    order_date: str = typer.Option("", "--date", "-d", help="日付 (YYYY-MM-DD)"),
    invoice: str = typer.Option("", "--invoice", "-i", help="インボイス番号"),
):
    """ファイルを電帳法準拠のファイル名にリネーム"""
    from acc_tool.drive.namer import generate_filename
    from acc_tool.models import OrderItem

    if not order_date:
        order_date = date.today().isoformat()

    d = date.fromisoformat(order_date)

    for f in files:
        if not f.exists():
            typer.echo(f"[!] ファイルが見つかりません: {f}", err=True)
            continue

        item = OrderItem(
            order_date=d,
            vendor=vendor or "不明",
            product_name=product or f.stem,
            amount=Decimal(amount),
            invoice_number=invoice,
        )

        new_name = generate_filename(item, ext=f.suffix)
        new_path = f.parent / new_name

        f.rename(new_path)
        typer.echo(f"[OK] {f.name} => {new_name}")


@app.command()
def check_dup(
    files: list[Path] = typer.Argument(..., help="チェック対象ファイル"),
    target_dir: Path = typer.Option(".", "--dir", help="照合対象ディレクトリ"),
):
    """重複チェック: 既存ファイルとの重複を検出"""
    from acc_tool.drive.dedup import check_duplicate
    from acc_tool.drive.namer import _parse_filename_to_item

    existing = [f.name for f in target_dir.iterdir() if f.is_file()]

    for f in files:
        # ファイル名から情報を抽出してチェック
        from acc_tool.drive.dedup import _parse_filename

        parts = _parse_filename(f.name)
        if not parts:
            typer.echo(f"[!] ファイル名が解析できません: {f.name}")
            continue

        f_date, f_vendor, f_amount = parts

        from acc_tool.models import OrderItem

        item = OrderItem(
            order_date=date(int(f_date[:4]), int(f_date[4:6]), int(f_date[6:8])),
            vendor=f_vendor,
            product_name="",
            amount=Decimal(f_amount),
        )

        match = check_duplicate(item, existing)
        if match:
            typer.echo(
                f"[!] 重複検出: {f.name}\n"
                f"  => 既存: {match.existing_filename}\n"
                f"  => タイプ: {match.match_type} (確度: {match.confidence:.0%})"
            )
        else:
            typer.echo(f"[OK] 重複なし: {f.name}")


if __name__ == "__main__":
    app()
