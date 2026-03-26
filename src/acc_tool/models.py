"""データモデル"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class Source(str, Enum):
    AMAZON = "Amazon"
    RAKUTEN = "楽天"
    RECEIPT = "レシート"
    YAHOO = "Yahoo"


@dataclass
class OrderItem:
    """EC注文の1明細"""

    order_date: date
    vendor: str  # 取引先名 (Amazon, 楽天, 店名)
    product_name: str
    amount: Decimal  # 税込金額
    invoice_number: str = ""  # インボイス番号 T+13桁
    source: Source = Source.AMAZON
    order_id: str = ""  # 注文番号
    payment_method: str = ""  # 支払方法

    @property
    def amount_int(self) -> int:
        return int(self.amount)


@dataclass
class JournalEntry:
    """仕訳1行"""

    entry_date: date
    debit_account: str  # 借方科目
    debit_amount: Decimal
    credit_account: str  # 貸方科目
    credit_amount: Decimal
    description: str  # 摘要
    confidence: str = "auto"  # auto / unknown


@dataclass
class ParseResult:
    """パーサーの返却値"""

    items: list[OrderItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source: Source = Source.AMAZON
