import { NextRequest, NextResponse } from "next/server";
import { adminAuth, adminDb } from "@/lib/firebase/admin";
import { getDriveAccessToken, ensureFolder } from "@/lib/google-drive";

const SOURCE_FOLDERS = ["amazon", "楽天", "yahoo", "カード領収書", "現金領収書"];

export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const decoded = await adminAuth.verifyIdToken(token);
    const uid = decoded.uid;

    const { fiscalYearStartMonth = 1 } = await req.json();
    const accessToken = await getDriveAccessToken(uid);

    // ルートフォルダ作成
    const rootId = await ensureFolder("acc", "root", accessToken);

    // 現在の年度フォルダを作成
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const fiscalYear = month < fiscalYearStartMonth ? year - 1 : year;

    const yearFolderId = await ensureFolder(`${fiscalYear}年度`, rootId, accessToken);

    // 未処理フォルダ作成
    const tempFolderId = await ensureFolder("未処理", rootId, accessToken);

    // 12ヶ月分のフォルダ + ソース別サブフォルダを作成
    for (let m = 1; m <= 12; m++) {
      const monthFolder = await ensureFolder(`${m}月`, yearFolderId, accessToken);
      for (const source of SOURCE_FOLDERS) {
        await ensureFolder(source, monthFolder, accessToken);
      }
    }

    // Firestoreに保存
    await adminDb.collection("users").doc(uid).set(
      { driveRootFolderId: rootId, driveTempFolderId: tempFolderId },
      { merge: true }
    );

    return NextResponse.json({ rootFolderId: rootId });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
