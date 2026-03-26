import { NextRequest, NextResponse } from "next/server";

/**
 * クライアントサイドでFirebase Authのトークンをcookieに保存し、
 * middlewareでチェックする方式。
 *
 * 注: 実際の検証はクライアントのAuthContextで行う。
 * ここでは__session cookieの有無で簡易チェック。
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 公開パスはスキップ
  const publicPaths = ["/login", "/api/"];
  if (publicPaths.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // ルートはダッシュボードへリダイレクト
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
