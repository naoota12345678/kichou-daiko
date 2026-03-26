import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";
import { adminAuth, adminDb } from "@/lib/firebase/admin";
import { getDriveAccessToken, ensureFolder, uploadFile } from "@/lib/google-drive";

/**
 * クイックアップロード: OCRなし、即Driveに保存
 * バックグラウンドで後からOCR処理する
 */
export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const decoded = await adminAuth.verifyIdToken(token);
    const uid = decoded.uid;

    const formData = await req.formData();
    const file = formData.get("file") as File;

    if (!file) {
      return NextResponse.json({ error: "file is required" }, { status: 400 });
    }

    const userDoc = await adminDb.collection("users").doc(uid).get();
    const settings = userDoc.data() || {};

    // トライアル期限チェック
    if (settings.plan !== "basic" && settings.createdAt) {
      const diffMs = Date.now() - new Date(settings.createdAt).getTime();
      if (diffMs > 7 * 24 * 60 * 60 * 1000) {
        return NextResponse.json({ error: "トライアル期間が終了しました。プランへのお申し込みが必要です。" }, { status: 403 });
      }
    }

    const rootFolderId = settings.driveRootFolderId;

    if (!rootFolderId) {
      return NextResponse.json({ error: "Driveが未設定です" }, { status: 400 });
    }

    const accessToken = await getDriveAccessToken(uid);
    const now = new Date();

    // Firestoreに保存済みの未処理フォルダIDを使う（なければ1回だけ作成）
    let tempFolderId = settings.driveTempFolderId;
    if (!tempFolderId) {
      tempFolderId = await ensureFolder("未処理", rootFolderId, accessToken);
      await adminDb.collection("users").doc(uid).set(
        { driveTempFolderId: tempFolderId },
        { merge: true }
      );
    }

    // ファイル名: 内容ハッシュベース（同じ画像は同じ名前 → 重複防止）
    const buffer = Buffer.from(await file.arrayBuffer());
    const hash = createHash("md5").update(buffer).digest("hex").slice(0, 12);
    const ext = file.name.includes(".") ? `.${file.name.split(".").pop()}` : ".jpg";
    const filename = `${hash}_未処理${ext}`;

    // Firestoreで重複チェック（即時反映、並列リクエストでも確実）
    const dedupRef = adminDb.collection("users").doc(uid).collection("upload_dedup").doc(hash);
    const dedupSnap = await dedupRef.get();
    if (dedupSnap.exists) {
      return NextResponse.json({ fileId: dedupSnap.data()?.fileId, filename, path: "acc/未処理", skipped: true });
    }

    // 先にロックを書き込み（他のリクエストがここに来ても弾かれる）
    await dedupRef.set({ filename, createdAt: new Date().toISOString() });

    // アップロード
    const fileId = await uploadFile(
      buffer,
      filename,
      tempFolderId,
      accessToken,
      file.type || "image/jpeg"
    );

    // fileIdを記録
    await dedupRef.update({ fileId });

    const path = `acc/未処理`;
    return NextResponse.json({ fileId, filename, path });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
