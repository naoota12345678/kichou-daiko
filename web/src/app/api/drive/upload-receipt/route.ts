import { NextRequest, NextResponse } from "next/server";
import { adminAuth, adminDb } from "@/lib/firebase/admin";
import { getDriveAccessToken, ensureFolder, uploadFile } from "@/lib/google-drive";

export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const decoded = await adminAuth.verifyIdToken(token);
    const uid = decoded.uid;

    const formData = await req.formData();
    const file = formData.get("file") as File;
    const date = formData.get("date") as string;
    const vendor = formData.get("vendor") as string;
    const amount = formData.get("amount") as string;
    const invoiceNumber = formData.get("invoiceNumber") as string;
    const receiptType = formData.get("receiptType") as string; // カード / 現金

    if (!file || !date || !amount) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    // ユーザー設定取得
    const userDoc = await adminDb.collection("users").doc(uid).get();
    const settings = userDoc.data() || {};
    const rootFolderId = settings.driveRootFolderId;
    const fiscalYearStartMonth = settings.fiscalYearStartMonth || 1;

    if (!rootFolderId) {
      return NextResponse.json({ error: "Driveが未設定です。セットアップしてください。" }, { status: 400 });
    }

    const accessToken = await getDriveAccessToken(uid);

    // フォルダパス: acc / {年度}年度 / {月}月 / カード領収書 or 現金領収書
    const [yearStr, monthStr] = date.split("-");
    const year = parseInt(yearStr);
    const month = parseInt(monthStr);
    const fiscalYear = month < fiscalYearStartMonth ? year - 1 : year;

    const folderName = receiptType === "カード" ? "カード領収書" : "現金領収書";

    const yearFolderId = await ensureFolder(`${fiscalYear}年度`, rootFolderId, accessToken);
    const monthFolderId = await ensureFolder(`${month}月`, yearFolderId, accessToken);
    const typeFolderId = await ensureFolder(folderName, monthFolderId, accessToken);

    // ファイル名生成
    const dateStr = date.replace(/-/g, "");
    const cleanVendor = (vendor || "不明").replace(/[\\/:*?"<>|\n\r\t]/g, "").slice(0, 20);
    const ext = file.name.includes(".") ? `.${file.name.split(".").pop()}` : ".jpg";
    let filename = `${dateStr}_${cleanVendor}_${amount}`;
    if (invoiceNumber) filename += `_${invoiceNumber}`;
    filename += ext;

    // アップロード
    const buffer = Buffer.from(await file.arrayBuffer());
    const fileId = await uploadFile(
      buffer,
      filename,
      typeFolderId,
      accessToken,
      file.type || "image/jpeg"
    );

    // CSVに追記（月フォルダに）
    const csvName = receiptType === "カード" ? "カード.csv" : "現金.csv";
    await appendToCsvViaApi(
      accessToken,
      monthFolderId,
      csvName,
      { date, vendor: vendor || "不明", amount, invoiceNumber }
    );

    return NextResponse.json({ fileId, filename });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

async function appendToCsvViaApi(
  accessToken: string,
  monthFolderId: string,
  csvName: string,
  item: { date: string; vendor: string; amount: string; invoiceNumber: string }
) {
  const DRIVE_API = "https://www.googleapis.com/drive/v3";

  // 既存CSV検索
  const query = `name='${csvName}' and '${monthFolderId}' in parents and trashed=false`;
  const searchRes = await fetch(
    `${DRIVE_API}/files?q=${encodeURIComponent(query)}&fields=files(id)`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const searchData = await searchRes.json();
  const existingFileId = searchData.files?.[0]?.id;

  // 既存CSVの内容を取得
  let existingContent = "";
  if (existingFileId) {
    const dlRes = await fetch(
      `${DRIVE_API}/files/${existingFileId}?alt=media`,
      { headers: { Authorization: `Bearer ${accessToken}` } }
    );
    existingContent = await dlRes.text();
  }

  // 新しい行を追加
  let csv = existingContent;
  if (!csv) {
    csv = "\ufeff日付,取引先,金額,インボイス番号\n";
  }
  csv += `${item.date},${item.vendor},${item.amount},${item.invoiceNumber}\n`;

  const csvBuffer = Buffer.from(csv, "utf-8");

  if (existingFileId) {
    // 上書き
    await fetch(
      `https://www.googleapis.com/upload/drive/v3/files/${existingFileId}?uploadType=media`,
      {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "text/csv",
        },
        body: csvBuffer,
      }
    );
  } else {
    // 新規作成
    const boundary = "csv_boundary";
    const meta = JSON.stringify({ name: csvName, parents: [monthFolderId] });
    const body =
      `--${boundary}\r\nContent-Type: application/json\r\n\r\n${meta}\r\n` +
      `--${boundary}\r\nContent-Type: text/csv\r\nContent-Transfer-Encoding: base64\r\n\r\n` +
      `${csvBuffer.toString("base64")}\r\n--${boundary}--`;

    await fetch(
      "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": `multipart/related; boundary=${boundary}`,
        },
        body,
      }
    );
  }
}
