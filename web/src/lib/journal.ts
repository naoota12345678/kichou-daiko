/** 仕訳CSV生成 (Python journal.py の TypeScript移植) */

import { classifyAccount } from "./rules";
import { CsvFormat, JournalEntry, OrderItem } from "./models";

/**
 * 注文データから仕訳エントリを生成
 * 貸方は全て「未払費用」で統一。借方科目はキーワードルールで推定。
 */
export function generateJournalEntries(items: OrderItem[]): JournalEntry[] {
  return items.map((item) => {
    const [account, confidence] = classifyAccount(item.productName, item.amount);
    return {
      entryDate: item.orderDate,
      debitAccount: account,
      debitAmount: item.amount,
      creditAccount: "未払費用",
      creditAmount: item.amount,
      description: `${item.vendor} ${item.productName}`,
      confidence,
    };
  });
}

/**
 * 仕訳CSV文字列を生成
 */
export function writeCsv(entries: JournalEntry[], fmt: CsvFormat = "generic"): string {
  const writer = FORMAT_WRITERS[fmt] ?? writeGeneric;
  return writer(entries);
}

/**
 * Shift_JIS用にバイト数で切り詰め (encoding-japanese使用時)
 */
export function truncateSjis(text: string, maxBytes: number): string {
  let result = "";
  let byteCount = 0;
  for (const ch of text) {
    // 半角1byte、全角2byte概算
    const chBytes = ch.charCodeAt(0) > 0x7f ? 2 : 1;
    if (byteCount + chBytes > maxBytes) break;
    result += ch;
    byteCount += chBytes;
  }
  return result;
}

function csvRow(fields: (string | number)[]): string {
  return fields
    .map((f) => {
      const s = String(f);
      if (s.includes(",") || s.includes('"') || s.includes("\n")) {
        return `"${s.replace(/"/g, '""')}"`;
      }
      return s;
    })
    .join(",");
}

function formatDate(dateStr: string, sep = "/"): string {
  const [y, m, d] = dateStr.split("-");
  return `${y}${sep}${m}${sep}${d}`;
}

function writeGeneric(entries: JournalEntry[]): string {
  const lines = [
    csvRow(["日付", "借方科目", "借方金額", "貸方科目", "貸方金額", "摘要"]),
    ...entries.map((e) =>
      csvRow([
        formatDate(e.entryDate),
        e.debitAccount,
        e.debitAmount,
        e.creditAccount,
        e.creditAmount,
        e.description,
      ])
    ),
  ];
  return lines.join("\n") + "\n";
}

function writeFreee(entries: JournalEntry[]): string {
  const lines = [
    csvRow([
      "取引日", "借方勘定科目", "借方金額(税込)",
      "貸方勘定科目", "貸方金額(税込)", "摘要",
    ]),
    ...entries.map((e) =>
      csvRow([
        formatDate(e.entryDate, "-"),
        e.debitAccount,
        e.debitAmount,
        e.creditAccount,
        e.creditAmount,
        e.description,
      ])
    ),
  ];
  return lines.join("\n") + "\n";
}

function writeYayoi(entries: JournalEntry[]): string {
  const lines = [
    csvRow([
      "識別フラグ", "伝票No.", "決算", "取引日付", "借方勘定科目",
      "借方金額", "貸方勘定科目", "貸方金額", "摘要",
    ]),
    ...entries.map((e, i) =>
      csvRow([
        2000,
        i + 1,
        "",
        formatDate(e.entryDate),
        e.debitAccount,
        e.debitAmount,
        e.creditAccount,
        e.creditAmount,
        e.description,
      ])
    ),
  ];
  return lines.join("\n") + "\n";
}

function writeMf(entries: JournalEntry[]): string {
  const lines = [
    csvRow([
      "取引No", "取引日", "借方勘定科目", "借方金額",
      "貸方勘定科目", "貸方金額", "摘要",
    ]),
    ...entries.map((e, i) =>
      csvRow([
        i + 1,
        formatDate(e.entryDate),
        e.debitAccount,
        e.debitAmount,
        e.creditAccount,
        e.creditAmount,
        e.description,
      ])
    ),
  ];
  return lines.join("\n") + "\n";
}

function writeZaimuR4(entries: JournalEntry[]): string {
  const lines = entries.map((e) => {
    const desc = truncateSjis(e.description, 48);
    return csvRow([
      formatDate(e.entryDate),
      e.debitAccount,
      e.debitAmount,
      e.creditAccount,
      e.creditAmount,
      desc,
    ]);
  });
  return lines.join("\n") + "\n";
}

const FORMAT_WRITERS: Record<CsvFormat, (entries: JournalEntry[]) => string> = {
  generic: writeGeneric,
  freee: writeFreee,
  yayoi: writeYayoi,
  mf: writeMf,
  zaimu_r4: writeZaimuR4,
};
