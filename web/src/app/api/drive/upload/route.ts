import { NextRequest, NextResponse } from "next/server";
import { adminAuth, adminDb } from "@/lib/firebase/admin";
import { getDriveAccessToken, ensureFolder, uploadFile, listFiles } from "@/lib/google-drive";
import { generateFilename, generateFolderPath } from "@/lib/namer";
import { checkDuplicate } from "@/lib/dedup";
import type { OrderItem, Source } from "@/lib/models";

export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const decoded = await adminAuth.verifyIdToken(token);
    const uid = decoded.uid;

    const formData = await req.formData();
    const file = formData.get("file") as File;
    const orderDate = formData.get("orderDate") as string;
    const vendor = formData.get("vendor") as string;
    const productName = formData.get("productName") as string;
    const amount = parseInt(formData.get("amount") as string) || 0;
    const invoiceNumber = (formData.get("invoiceNumber") as string) || "";
    const source = (formData.get("source") as Source) || "レシート";

    if (!file || !orderDate || !vendor || !amount) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    const item: OrderItem = {
      orderDate,
      vendor,
      productName: productName || vendor,
      amount,
      invoiceNumber: invoiceNumber || undefined,
      source,
    };

    const accessToken = await getDriveAccessToken(uid);

    // ユーザー設定取得
    const userDoc = await adminDb.collection("users").doc(uid).get();
    const settings = userDoc.data() || {};
    const rootFolderId = settings.driveRootFolderId;
    const fiscalYearStartMonth = settings.fiscalYearStartMonth || 1;

    if (!rootFolderId) {
      return NextResponse.json(
        { error: "Drive not set up. Run setup first." },
        { status: 400 }
      );
    }

    // フォルダパス生成 & 確保
    const [year, month] = orderDate.split("-").map(Number);
    const folderPath = generateFolderPath(fiscalYearStartMonth, year, month);
    const pathParts = folderPath.split("/");

    let currentFolderId = rootFolderId;
    for (const part of pathParts) {
      currentFolderId = await ensureFolder(part, currentFolderId, accessToken);
    }

    // 重複チェック
    const existingFiles = await listFiles(currentFolderId, accessToken);
    const duplicate = checkDuplicate(item, existingFiles);

    // ファイル名生成
    const ext = file.name.includes(".")
      ? `.${file.name.split(".").pop()}`
      : ".pdf";
    const filename = generateFilename(item, ext);

    // アップロード
    const buffer = Buffer.from(await file.arrayBuffer());
    const fileId = await uploadFile(
      buffer,
      filename,
      currentFolderId,
      accessToken,
      file.type || "application/octet-stream"
    );

    return NextResponse.json({
      fileId,
      filename,
      duplicate: duplicate || undefined,
    });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
