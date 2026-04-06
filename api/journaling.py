"""2段階仕訳エンジン — Haiku一次判断 → Opus二次判断"""

from __future__ import annotations

import json
import os
import re

import anthropic

from models import JournalPattern, ReceiptData, JournalEntry


client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def _build_pattern_text(patterns: list[JournalPattern]) -> str:
    """仕訳パターンを参照テキストに変換"""
    if not patterns:
        return "（パターン未登録）"

    lines = []
    for p in patterns:
        keywords = ", ".join(p.keywords) if p.keywords else "(キーワードなし)"
        line = (
            f"- キーワード: {keywords} → "
            f"借方: {p.debit_account}({p.debit_code}) / "
            f"貸方: {p.credit_account}({p.credit_code}) "
            f"税率: {p.tax_rate}% "
            f"税区分: {p.tax_category}"
        )
        if p.vendor_name:
            line += f" 取引先: {p.vendor_name}"
        if p.description_template:
            line += f" 摘要: {p.description_template}"
        lines.append(line)
    return "\n".join(lines)


def judge_stage1(receipt: ReceiptData, patterns: list[JournalPattern], rules: list[str] | None = None) -> JournalEntry:
    """Haiku一次判断: OCRテキスト + パターンマスタから仕訳を生成"""

    pattern_text = _build_pattern_text(patterns)

    rules_text = ""
    if rules:
        rules_text = "\n■ この顧問先の追加仕訳ルール（必ず従ってください）:\n"
        for i, rule in enumerate(rules, 1):
            rules_text += f"{i}. {rule}\n"

    prompt = f"""あなたは記帳代行の仕訳担当です。以下のレシート情報から仕訳を作成してください。

■ レシート情報:
- 取引先: {receipt.vendor}
- 金額: {receipt.amount}円
- 日付: {receipt.date}
- 支払方法: {receipt.payment_method}
- 税率: {receipt.tax_rate}%
- インボイス番号: {receipt.invoice_number or "なし"}
- 品目: {", ".join(receipt.items) if receipt.items else "不明"}

■ OCRテキスト（参考）:
{receipt.ocr_text[:2000]}

■ 仕訳パターンマスタ（この中から最も適切なものを選んでください）:
{pattern_text}
{rules_text}
■ ルール:
1. パターンマスタのキーワードと取引先名・品目を照合し、最適な仕訳パターンを選ぶ
2. 取引先名のゆらぎを吸収する（例: ツルハドラッグ/ツルハ/TSURUHA → 同じ取引先）
3. 支払方法に応じて貸方を判断:
   - 現金 → 現金 or 小口現金
   - カード → 未払金 or 買掛金（パターンの貸方科目に従う）
4. 税率はレシート記載を優先（8%軽減税率の食品等に注意）
5. パターンに該当するものがない場合は confidence: "low" とする
6. 摘要には得意先マスタにマッチした得意先名をそのまま入れる（マスタがない場合はOCRの取引先名）
7. 科目コード（debit_code, credit_code）は数値のみ、先頭ゼロなし（例: "141"、"100"）
8. 補助コードは別途後処理するのでJSONには含めないこと
9. 科目コードマスタが追加ルールにある場合、必ずその中のコードを使うこと（マスタにないコードは使わない）

以下のJSON形式で返してください:
{{
  "debit_account": "借方科目名",
  "debit_code": "借方科目コード（数値、先頭ゼロなし）",
  "credit_account": "貸方科目名",
  "credit_code": "貸方科目コード（数値、先頭ゼロなし）",
  "tax_rate": "10",
  "tax_category": "税区分",
  "description": "摘要",
  "vendor": "正規化した取引先名",
  "confidence": "high" or "low"
}}
JSONのみ返してください。"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    ai_text = response.content[0].text if response.content else ""
    json_match = re.search(r"\{[\s\S]*\}", ai_text)
    result = json.loads(json_match.group()) if json_match else {}

    # 科目コードの先頭ゼロを除去
    debit_code = result.get("debit_code", "")
    credit_code = result.get("credit_code", "")
    if debit_code and debit_code.isdigit():
        debit_code = str(int(debit_code))
    if credit_code and credit_code.isdigit():
        credit_code = str(int(credit_code))

    entry = JournalEntry(
        entry_date=receipt.date,
        debit_account=result.get("debit_account", ""),
        debit_code=debit_code,
        debit_amount=receipt.amount,
        debit_tax_category=result.get("tax_category", ""),
        credit_account=result.get("credit_account", ""),
        credit_code=credit_code,
        credit_amount=receipt.amount,
        credit_tax_category=result.get("tax_category", ""),
        tax_rate=result.get("tax_rate", receipt.tax_rate),
        description=result.get("description", ""),
        vendor=result.get("vendor", receipt.vendor),
        confidence=result.get("confidence", "low"),
        reasoning="Haiku自動判定",
    )

    return entry


def judge_stage2(
    receipt: ReceiptData,
    haiku_entry: JournalEntry,
    patterns: list[JournalPattern],
) -> JournalEntry:
    """Opus二次判断: Haikuがlow confidenceだった仕訳を再判定＋根拠生成"""

    pattern_text = _build_pattern_text(patterns)

    prompt = f"""あなたは経験豊富な記帳代行の税理士補助者です。
一次判定（AI）で確信度が低かった仕訳を再判定し、判断根拠を明確に残してください。

■ レシート情報:
- 取引先: {receipt.vendor}
- 金額: {receipt.amount}円
- 日付: {receipt.date}
- 支払方法: {receipt.payment_method}
- 税率: {receipt.tax_rate}%
- インボイス番号: {receipt.invoice_number or "なし"}
- 品目: {", ".join(receipt.items) if receipt.items else "不明"}

■ OCRテキスト:
{receipt.ocr_text[:3000]}

■ 一次判定結果（Haiku）:
- 借方: {haiku_entry.debit_account}({haiku_entry.debit_code})
- 貸方: {haiku_entry.credit_account}({haiku_entry.credit_code})
- 摘要: {haiku_entry.description}
- 確信度: low

■ 仕訳パターンマスタ:
{pattern_text}

■ 判断ポイント:
1. パターンマスタに近いものがあるか再確認（ゆらぎ含む）
2. なければ、レシートの内容から最も適切な勘定科目を判断
3. 税率（10%/8%）の妥当性を確認（食品・飲料は8%の可能性）
4. 10万円以上なら資産計上の可能性を検討
5. 判断根拠を具体的に記載（「〇〇の品目から△△費と判断」等）
6. 科目コードマスタがある場合、必ずその中のコードを使うこと

以下のJSON形式で返してください:
{{
  "debit_account": "借方科目名",
  "debit_code": "借方科目コード",
  "credit_account": "貸方科目名",
  "credit_code": "貸方科目コード",
  "tax_rate": "10",
  "tax_category": "税区分",
  "description": "摘要",
  "vendor": "正規化した取引先名",
  "confidence": "high" or "low",
  "reasoning": "判断根拠を3文程度で具体的に"
}}
JSONのみ返してください。"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    ai_text = response.content[0].text if response.content else ""
    json_match = re.search(r"\{[\s\S]*\}", ai_text)
    result = json.loads(json_match.group()) if json_match else {}

    entry = JournalEntry(
        entry_date=receipt.date,
        debit_account=result.get("debit_account", haiku_entry.debit_account),
        debit_code=result.get("debit_code", haiku_entry.debit_code),
        debit_amount=receipt.amount,
        debit_tax_category=result.get("tax_category", ""),
        credit_account=result.get("credit_account", haiku_entry.credit_account),
        credit_code=result.get("credit_code", haiku_entry.credit_code),
        credit_amount=receipt.amount,
        credit_tax_category=result.get("tax_category", ""),
        tax_rate=result.get("tax_rate", receipt.tax_rate),
        description=result.get("description", haiku_entry.description),
        vendor=result.get("vendor", receipt.vendor),
        confidence=result.get("confidence", "high"),
        reasoning=result.get("reasoning", "Opus再判定"),
    )

    return entry


def process_receipt(
    receipt: ReceiptData,
    patterns: list[JournalPattern],
    rules: list[str] | None = None,
) -> JournalEntry:
    """レシート→仕訳 の2段階処理パイプライン"""

    # Stage 1: Haiku
    entry = judge_stage1(receipt, patterns, rules)

    # Stage 2: confidence=low ならOpusで再判定（現在テスト中：Haikuのみで運用）
    # if entry.confidence == "low":
    #     print(f"[仕訳] Low confidence → Opus再判定: {receipt.vendor} ¥{receipt.amount}")
    #     entry = judge_stage2(receipt, entry, patterns)
    if entry.confidence == "low":
        print(f"[仕訳] Low confidence（Opusスキップ中）: {receipt.vendor} ¥{receipt.amount}")

    return entry
