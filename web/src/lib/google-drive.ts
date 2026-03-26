/** Google Drive API ヘルパー (サーバーサイド) */

import { adminDb } from "./firebase/admin";

const DRIVE_API = "https://www.googleapis.com/drive/v3";
const UPLOAD_API = "https://www.googleapis.com/upload/drive/v3";

/**
 * Firestoreからrefresh tokenを取得し、access tokenを生成
 */
export async function getDriveAccessToken(uid: string): Promise<string> {
  const tokenDoc = await adminDb
    .collection("users")
    .doc(uid)
    .collection("private")
    .doc("tokens")
    .get();

  const refreshToken = tokenDoc.data()?.driveRefreshToken;
  if (!refreshToken) {
    throw new Error("Drive not connected. Please authorize Google Drive first.");
  }

  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: process.env.GOOGLE_CLIENT_ID!,
      client_secret: process.env.GOOGLE_CLIENT_SECRET!,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(`Token refresh failed: ${data.error_description || data.error}`);
  }

  return data.access_token;
}

/**
 * フォルダを検索or作成して返す
 */
export async function ensureFolder(
  name: string,
  parentId: string,
  accessToken: string
): Promise<string> {
  // 既存フォルダ検索
  const query = `name='${name}' and '${parentId}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false`;
  const searchRes = await fetch(
    `${DRIVE_API}/files?q=${encodeURIComponent(query)}&fields=files(id,name)`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const searchData = await searchRes.json();

  if (searchData.files?.length > 0) {
    return searchData.files[0].id;
  }

  // 新規作成
  const createRes = await fetch(`${DRIVE_API}/files`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      mimeType: "application/vnd.google-apps.folder",
      parents: [parentId],
    }),
  });
  const createData = await createRes.json();
  return createData.id;
}

/**
 * ファイルをDriveにアップロード
 */
export async function uploadFile(
  file: Buffer,
  filename: string,
  folderId: string,
  accessToken: string,
  mimeType = "application/pdf"
): Promise<string> {
  const metadata = {
    name: filename,
    parents: [folderId],
  };

  const boundary = "acc_tool_boundary";
  const body =
    `--${boundary}\r\n` +
    `Content-Type: application/json; charset=UTF-8\r\n\r\n` +
    `${JSON.stringify(metadata)}\r\n` +
    `--${boundary}\r\n` +
    `Content-Type: ${mimeType}\r\n` +
    `Content-Transfer-Encoding: base64\r\n\r\n` +
    `${file.toString("base64")}\r\n` +
    `--${boundary}--`;

  const res = await fetch(
    `${UPLOAD_API}/files?uploadType=multipart&fields=id,name`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": `multipart/related; boundary=${boundary}`,
      },
      body,
    }
  );

  const data = await res.json();
  if (!res.ok) {
    throw new Error(`Upload failed: ${data.error?.message || JSON.stringify(data)}`);
  }
  return data.id;
}

/**
 * フォルダ内ファイル一覧
 */
export async function listFiles(
  folderId: string,
  accessToken: string
): Promise<string[]> {
  const query = `'${folderId}' in parents and trashed=false`;
  const res = await fetch(
    `${DRIVE_API}/files?q=${encodeURIComponent(query)}&fields=files(name)&pageSize=1000`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const data = await res.json();
  return (data.files || []).map((f: { name: string }) => f.name);
}
