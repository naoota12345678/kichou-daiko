"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { TrialBanner } from "@/components/trial-banner";
import { usePlan } from "@/hooks/use-plan";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const { trialExpired } = usePlan();

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <TrialBanner />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">ダッシュボード</h1>

        {trialExpired ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-lg font-medium mb-2">無料トライアル期間が終了しました</p>
              <p className="text-sm text-muted-foreground mb-4">
                引き続きご利用いただくには、プランへのお申し込みが必要です。
              </p>
              <p className="text-sm text-muted-foreground">
                月額 <strong>1,480円</strong>（税別）・リリース記念 <strong>980円</strong>
              </p>
              <p className="text-sm text-muted-foreground mt-2">
                お申し込み: <a href="mailto:contact@romu.ai" className="underline text-blue-600">contact@romu.ai</a>
              </p>
              <p className="text-xs text-muted-foreground mt-4">
                ※ Google Driveに保存済みのデータはそのままお使いいただけます
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6 grid-cols-1 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">EC注文取得</CardTitle>
                <CardDescription>
                  Amazon・楽天・Yahooから自動取得
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Link href="/scrape">
                  <Button className="w-full">注文を取得</Button>
                </Link>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">レシート撮影</CardTitle>
                <CardDescription>
                  撮影してDriveに保存・自動読み取り
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Link href="/receipts/upload">
                  <Button variant="outline" className="w-full">撮影・アップロード</Button>
                </Link>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">仕訳ルール</CardTitle>
                <CardDescription>
                  顧問先ごとの仕訳ルールを管理
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Link href="/rules">
                  <Button variant="outline" className="w-full">ルール管理</Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
