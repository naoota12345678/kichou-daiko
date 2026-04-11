"""データモデル"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ReceiptData:
    vendor: str = ""
    amount: int = 0
    date: str = ""
    invoice_number: str = ""
    payment_method: str = "現金"
    tax_rate: str = "10"
    items: list[str] = field(default_factory=list)
    ocr_text: str = ""


@dataclass
class JournalEntry:
    id: str = ""
    entry_date: str = ""
    debit_account: str = ""
    debit_code: str = ""
    debit_amount: int = 0
    debit_tax_category: str = ""
    debit_sub_code: str = ""
    debit_sub_name: str = ""
    credit_account: str = ""
    credit_code: str = ""
    credit_amount: int = 0
    credit_tax_category: str = ""
    credit_sub_code: str = ""
    credit_sub_name: str = ""
    tax_rate: str = "10"
    description: str = ""
    vendor: str = ""
    confidence: str = ""
    reasoning: str = ""
    duplicate_flag: str = ""


@dataclass
class JournalPattern:
    id: str = ""
    keywords: list[str] = field(default_factory=list)
    vendor_name: str = ""
    debit_account: str = ""
    debit_code: str = ""
    credit_account: str = ""
    credit_code: str = ""
    tax_rate: str = "10"
    tax_category: str = ""
    description_template: str = ""
