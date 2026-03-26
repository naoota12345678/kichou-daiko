import { NextRequest, NextResponse } from "next/server";
import { adminDb } from "@/lib/firebase/admin";

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code");
  const state = req.nextUrl.searchParams.get("state"); // uid
  const origin = req.nextUrl.origin;

  if (!code) {
    return NextResponse.redirect(
      new URL("/setup?drive=error&msg=no_code", origin)
    );
  }

  try {
    // 認可コードをトークンに交換
    const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: process.env.GOOGLE_CLIENT_ID!,
        client_secret: process.env.GOOGLE_CLIENT_SECRET!,
        redirect_uri: `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/drive/callback`,
        grant_type: "authorization_code",
      }),
    });

    const tokenData = await tokenRes.json();

    if (!tokenRes.ok) {
      const msg = encodeURIComponent(tokenData.error_description || tokenData.error || "unknown");
      return NextResponse.redirect(
        new URL(`/setup?drive=error&msg=${msg}`, origin)
      );
    }

    // refresh tokenをFirestoreに保存
    if (state) {
      await adminDb
        .collection("users")
        .doc(state)
        .collection("private")
        .doc("tokens")
        .set(
          { driveRefreshToken: tokenData.refresh_token },
          { merge: true }
        );

      await adminDb
        .collection("users")
        .doc(state)
        .set({ driveConnected: true }, { merge: true });
    }

    return NextResponse.redirect(
      new URL("/setup?drive=connected", origin)
    );
  } catch (error: any) {
    const msg = encodeURIComponent(error.message || "unknown");
    return NextResponse.redirect(
      new URL(`/setup?drive=error&msg=${msg}`, origin)
    );
  }
}
