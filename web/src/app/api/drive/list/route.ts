import { NextRequest, NextResponse } from "next/server";
import { adminAuth, adminDb } from "@/lib/firebase/admin";
import { getDriveAccessToken, listFiles, ensureFolder } from "@/lib/google-drive";

export async function GET(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const decoded = await adminAuth.verifyIdToken(token);
    const uid = decoded.uid;

    const userDoc = await adminDb.collection("users").doc(uid).get();
    const settings = userDoc.data() || {};
    const rootFolderId = settings.driveRootFolderId;

    if (!rootFolderId) {
      return NextResponse.json({ files: [] });
    }

    const accessToken = await getDriveAccessToken(uid);

    // 全サブフォルダのファイルを再帰的に取得
    const allFiles = await collectAllFiles(rootFolderId, accessToken);

    return NextResponse.json({ files: allFiles });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

async function collectAllFiles(
  folderId: string,
  accessToken: string
): Promise<string[]> {
  const DRIVE_API = "https://www.googleapis.com/drive/v3";
  const files: string[] = [];

  // フォルダ内のファイル取得
  const query = `'${folderId}' in parents and trashed=false`;
  const res = await fetch(
    `${DRIVE_API}/files?q=${encodeURIComponent(query)}&fields=files(id,name,mimeType)&pageSize=1000`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const data = await res.json();

  for (const item of data.files || []) {
    if (item.mimeType === "application/vnd.google-apps.folder") {
      const subFiles = await collectAllFiles(item.id, accessToken);
      files.push(...subFiles);
    } else {
      files.push(item.name);
    }
  }

  return files;
}
