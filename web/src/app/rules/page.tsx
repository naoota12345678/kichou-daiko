"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { ClientSelector } from "@/components/client-selector";
import { JournalRules } from "@/components/journal-rules";

export default function RulesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [clientId, setClientId] = useState("");
  const [clientName, setClientName] = useState("");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
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
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">仕訳ルール管理</h1>

        <div className="mb-6">
          <ClientSelector
            selectedId={clientId}
            onSelect={(id, name) => {
              setClientId(id);
              setClientName(name);
            }}
          />
        </div>

        {clientId ? (
          <JournalRules clientId={clientId} />
        ) : (
          <p className="text-sm text-muted-foreground">顧問先を選択してください</p>
        )}
      </main>
    </div>
  );
}
