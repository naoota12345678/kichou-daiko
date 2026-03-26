"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { SetupWizard } from "@/components/setup-wizard";

export default function SetupPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

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
      <main className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">初回セットアップ</h1>
        <Suspense fallback={<p className="text-muted-foreground">読み込み中...</p>}>
          <SetupWizard />
        </Suspense>
      </main>
    </div>
  );
}
