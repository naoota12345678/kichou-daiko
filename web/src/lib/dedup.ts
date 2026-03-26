/** 重複チェック (Python dedup.py の TypeScript移植) */

import { OrderItem } from "./models";

export interface DuplicateMatch {
  existingFilename: string;
  matchType: "exact" | "date_amount" | "similar";
  confidence: number; // 0.0 - 1.0
}

/**
 * 既存ファイル名一覧と照合して重複を検出
 */
export function checkDuplicate(
  item: OrderItem,
  existingFiles: string[]
): DuplicateMatch | null {
  const itemDateStr = item.orderDate.replace(/-/g, "");
  const itemAmount = String(item.amount);
  const itemVendor = item.vendor;

  for (const fname of existingFiles) {
    const parts = parseFilename(fname);
    if (!parts) continue;

    const [fDate, fVendor, fAmount] = parts;

    // exact: 日付 + 金額 + 取引先 完全一致
    if (fDate === itemDateStr && fAmount === itemAmount && fVendor === itemVendor) {
      return { existingFilename: fname, matchType: "exact", confidence: 1.0 };
    }

    // date_amount: 日付±1日 + 金額一致
    if (fAmount === itemAmount && dateWithin(itemDateStr, fDate, 1)) {
      return { existingFilename: fname, matchType: "date_amount", confidence: 0.8 };
    }

    // similar: 日付±3日 + 金額一致
    if (fAmount === itemAmount && dateWithin(itemDateStr, fDate, 3)) {
      return { existingFilename: fname, matchType: "similar", confidence: 0.6 };
    }
  }

  return null;
}

function parseFilename(fname: string): [string, string, string] | null {
  // 拡張子除去
  const stem = fname.replace(/\.[^.]+$/, "");
  const parts = stem.split("_");
  if (parts.length < 4) return null;

  const fDate = parts[0];
  if (!/^\d{8}$/.test(fDate)) return null;

  const fVendor = parts[1];

  // 金額は末尾側（インボイス番号がある場合は末尾から2番目）
  let fAmount = "";
  for (let i = parts.length - 1; i >= 2; i--) {
    if (/^T\d{13}$/.test(parts[i])) continue;
    if (/^\d+$/.test(parts[i])) {
      fAmount = parts[i];
      break;
    }
  }

  if (!fAmount) return null;
  return [fDate, fVendor, fAmount];
}

function dateWithin(date1Str: string, date2Str: string, days: number): boolean {
  try {
    const d1 = new Date(
      parseInt(date1Str.slice(0, 4)),
      parseInt(date1Str.slice(4, 6)) - 1,
      parseInt(date1Str.slice(6, 8))
    );
    const d2 = new Date(
      parseInt(date2Str.slice(0, 4)),
      parseInt(date2Str.slice(4, 6)) - 1,
      parseInt(date2Str.slice(6, 8))
    );
    const diffMs = Math.abs(d1.getTime() - d2.getTime());
    return diffMs / (1000 * 60 * 60 * 24) <= days;
  } catch {
    return false;
  }
}
