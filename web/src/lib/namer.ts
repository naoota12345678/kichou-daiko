/** 電帳法準拠ファイル名生成 (Python namer.py の TypeScript移植) */

import { OrderItem } from "./models";

/**
 * 電帳法準拠のファイル名を生成
 * 形式: {YYYYMMDD}_{取引先}_{品名}_{金額}[_{インボイス番号}].ext
 */
export function generateFilename(item: OrderItem, ext = ".pdf"): string {
  const dateStr = item.orderDate.replace(/-/g, "");
  const parts = [
    dateStr,
    sanitize(item.vendor),
    truncate(sanitize(item.productName), 30),
    String(item.amount),
  ];

  if (item.invoiceNumber) {
    parts.push(item.invoiceNumber);
  }

  return parts.join("_") + ext;
}

/**
 * レシート撮影画像のファイル名を生成
 * 形式: {YYYYMMDD}_レシート_{連番}.ext
 */
export function generateReceiptFilename(
  seq: number,
  captureDateStr: string,
  ext = ".jpg"
): string {
  return `${captureDateStr}_レシート_${String(seq).padStart(3, "0")}${ext}`;
}

/**
 * 年度/月のフォルダパスを生成
 * 例: "2025年度/04月/領収書"
 */
export function generateFolderPath(
  fiscalYearStartMonth: number,
  year: number,
  month: number
): string {
  const fiscalYear = month < fiscalYearStartMonth ? year - 1 : year;
  return `${fiscalYear}年度/${String(month).padStart(2, "0")}月/領収書`;
}

function sanitize(text: string): string {
  // NFKC正規化
  let s = text.normalize("NFKC");
  // ファイル名に使えない文字を除去
  s = s.replace(/[\\/:*?"<>|\n\r\t]/g, "");
  // 連続スペースを1つに
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

function truncate(text: string, maxLen = 30): string {
  return text.length <= maxLen ? text : text.slice(0, maxLen);
}
