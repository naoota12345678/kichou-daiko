"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { ClientSelector } from "@/components/client-selector";
import { listReceipts } from "@/lib/api";
import Link from "next/link";

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [clientId, setClientId] = useState("");
  const [clientName, setClientName] = useState("");

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  // 選択状態をlocalStorageに保存/復元
  useEffect(() => {
    const saved = localStorage.getItem("selectedClient");
    if (saved) {
      try {
        const { id, name } = JSON.parse(saved);
        if (id) { setClientId(id); setClientName(name); }
      } catch {}
    }
  }, []);

  const handleSelect = (id: string, name: string) => {
    setClientId(id);
    setClientName(name);
    localStorage.setItem("selectedClient", JSON.stringify({ id, name }));
    // Cloud Runウォームアップ（バックグラウンドで呼んで起こす）
    listReceipts(id).catch(() => {});
  };

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
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">記帳代行ツール</h1>

        <div className="mb-6">
          <ClientSelector selectedId={clientId} onSelect={handleSelect} />
        </div>

        {clientId ? (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            <Link href={`/receipts?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}>
              <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow cursor-pointer">
                <h2 className="font-bold text-lg mb-1">レシートアップロード</h2>
                <p className="text-sm text-muted-foreground">撮影してDriveに保存・自動仕訳</p>
              </div>
            </Link>

            <Link href={`/handwritten?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}>
              <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow cursor-pointer">
                <h2 className="font-bold text-lg mb-1">手書き領収書</h2>
                <p className="text-sm text-muted-foreground">手書き領収書の読み取り・仕訳</p>
              </div>
            </Link>

            <Link href={`/journals?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}>
              <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow cursor-pointer">
                <h2 className="font-bold text-lg mb-1">仕訳一覧</h2>
                <p className="text-sm text-muted-foreground">確認・修正・確定</p>
              </div>
            </Link>

            <Link href={`/rules?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}>
              <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow cursor-pointer">
                <h2 className="font-bold text-lg mb-1">仕訳ルール</h2>
                <p className="text-sm text-muted-foreground">パターン・ルールを管理</p>
              </div>
            </Link>

            <Link href={`/csv?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}>
              <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow cursor-pointer">
                <h2 className="font-bold text-lg mb-1">CSV出力</h2>
                <p className="text-sm text-muted-foreground">財務応援R4形式 / 汎用CSV</p>
              </div>
            </Link>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground bg-white rounded-lg shadow-sm p-6">
            顧問先を選択してください。新しい顧問先は「+ 追加」から登録できます。
          </p>
        )}
      </main>
    </div>
  );
}
