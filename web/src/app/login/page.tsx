"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";

export default function LoginPage() {
  const { user, loading, signIn, error } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [user, loading, router]);

  if (loading || user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (signingIn) return;
    setSigningIn(true);
    try {
      await signIn(email, password);
    } finally {
      setSigningIn(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white">
      <h1 className="mb-8 text-3xl font-bold">記帳代行ツール</h1>
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardDescription>
            レシートから仕訳を自動生成
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <div>
              <label className="text-sm text-muted-foreground">メールアドレス</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full mt-1 p-2 border rounded"
                required
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">パスワード</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full mt-1 p-2 border rounded"
                required
              />
            </div>
            <Button type="submit" size="lg" disabled={signingIn} className="w-full">
              {signingIn ? "ログイン中..." : "ログイン"}
            </Button>
            {error && (
              <p className="text-center text-sm text-red-600">{error}</p>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
