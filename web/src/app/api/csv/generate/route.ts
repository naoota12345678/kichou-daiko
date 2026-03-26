import { NextRequest, NextResponse } from "next/server";
import { adminAuth, adminDb } from "@/lib/firebase/admin";
import { getDriveAccessToken } from "@/lib/google-drive";
import { generateJournalEntries, writeCsv } from "@/lib/journal";
import type { CsvFormat, OrderItem } from "@/lib/models";

export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const decoded = await adminAuth.verifyIdToken(token);
    const uid = decoded.uid;

    const { format = "generic", startDate, endDate } = await req.json();

    const userDoc = await adminDb.collection("users").doc(uid).get();
    const settings = userDoc.data() || {};
    const rootFolderId = settings.driveRootFolderId;

    if (!rootFolderId) {
      return NextResponse.json({ error: "Drive not set up" }, { status: 400 });
    }

    const accessToken = await getDriveAccessToken(uid);

    // Driveからファイル一覧取得→ファイル名パースしてOrderItemに変換
    const allFiles = await collectAllFilenames(rootFolderId, accessToken);
    const items = parseFilenamesAsOrderItems(allFiles, startDate, endDate);

    // 仕訳生成
    const entries = generateJournalEntries(items);
    const csv = writeCsv(entries, format as CsvFormat);

    return NextResponse.json({
      csv,
      entries,
      count: entries.length,
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

async function collectAllFilenames(
  folderId: string,
  accessToken: string
): Promise<string[]> {
  const DRIVE_API = "https://www.googleapis.com/drive/v3";
  const files: string[] = [];

  const query = `'${folderId}' in parents and trashed=false`;
  const res = await fetch(
    `${DRIVE_API}/files?q=${encodeURIComponent(query)}&fields=files(id,name,mimeType)&pageSize=1000`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const data = await res.json();

  for (const item of data.files || []) {
    if (item.mimeType === "application/vnd.google-apps.folder") {
      const sub = await collectAllFilenames(item.id, accessToken);
      files.push(...sub);
    } else {
      files.push(item.name);
    }
  }

  return files;
}

/**
 * 電帳法ファイル名からOrderItemを復元
 * 形式: YYYYMMDD_取引先_品名_金額[_インボイス番号].ext
 */
function parseFilenamesAsOrderItems(
  filenames: string[],
  startDate?: string,
  endDate?: string
): OrderItem[] {
  const items: OrderItem[] = [];

  for (const fname of filenames) {
    const stem = fname.replace(/\.[^.]+$/, "");
    const parts = stem.split("_");
    if (parts.length < 4 || !/^\d{8}$/.test(parts[0])) continue;

    const d = parts[0];
    const dateStr = `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;

    // 期間フィルタ
    if (startDate && dateStr < startDate) continue;
    if (endDate && dateStr > endDate) continue;

    const vendor = parts[1];

    // 金額を見つける
    let amount = 0;
    let invoiceNumber = "";
    for (let i = parts.length - 1; i >= 2; i--) {
      if (/^T\d{13}$/.test(parts[i])) {
        invoiceNumber = parts[i];
        continue;
      }
      if (/^\d+$/.test(parts[i])) {
        amount = parseInt(parts[i]);
        break;
      }
    }

    // 品名 (金額・インボイスを除いた中間部分)
    const productName = parts.slice(2, -1).filter(
      (p) => !/^\d+$/.test(p) && !/^T\d{13}$/.test(p)
    ).join("_") || vendor;

    items.push({
      orderDate: dateStr,
      vendor,
      productName,
      amount,
      invoiceNumber: invoiceNumber || undefined,
      source: "レシート",
    });
  }

  return items.sort((a, b) => a.orderDate.localeCompare(b.orderDate));
}
