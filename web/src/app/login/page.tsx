"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** LINEなどアプリ内ブラウザかどうかを判定 */
function isInAppBrowser(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  return /Line|Instagram|FBAN|FBAV|Twitter|wv|WebView/i.test(ua);
}

export default function LoginPage() {
  const { user, loading, signInWithGoogle, error } = useAuth();
  const router = useRouter();
  const [signingIn, setSigningIn] = useState(false);
  const [inApp, setInApp] = useState(false);

  useEffect(() => {
    setInApp(isInAppBrowser());
  }, []);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [user, loading, router]);

  // ログイン済みまたは確認中はローディング表示
  if (loading || user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  const handleLogin = async () => {
    if (signingIn) return;
    setSigningIn(true);
    try {
      await signInWithGoogle();
    } catch {
      setSigningIn(false);
    }
  };

  /** 外部ブラウザで開くためのURLコピー */
  const handleCopyUrl = () => {
    navigator.clipboard.writeText(window.location.href);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white">
      <img src="/logo.png" alt="dentyo" className="mb-8 w-96" />
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardDescription>
            電子帳簿保存法対応の経理自動化ツール
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {inApp ? (
            <>
              <div className="rounded-md border border-orange-200 bg-orange-50 p-4 text-center">
                <p className="text-sm font-medium text-orange-800">
                  アプリ内ブラウザではGoogleログインが使えません
                </p>
                <p className="mt-2 text-xs text-orange-700">
                  右上のメニュー「…」から「ブラウザで開く」を選択するか、
                  下のボタンでURLをコピーしてChromeやSafariで開いてください
                </p>
              </div>
              <Button size="lg" variant="outline" onClick={handleCopyUrl} className="w-full">
                URLをコピー
              </Button>
            </>
          ) : (
            <>
              <p className="text-center text-sm text-muted-foreground">
                Googleアカウントでログインして領収書管理を始めましょう
              </p>
              <Button size="lg" onClick={handleLogin} disabled={signingIn} className="w-full">
                {signingIn ? "ログイン中..." : "Googleでログイン"}
              </Button>
              {error && (
                <p className="text-center text-sm text-red-600 break-all">{error}</p>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
