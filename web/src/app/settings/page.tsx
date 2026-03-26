"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { getClientDb } from "@/lib/firebase/client";
import { Header } from "@/components/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import type { UserSettings } from "@/lib/models";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SettingsMap = Record<string, any>;

const SOFTWARE_OPTIONS = [
  { value: "generic", label: "汎用CSV" },
  { value: "freee", label: "freee" },
  { value: "yayoi", label: "弥生会計" },
  { value: "mf", label: "MFクラウド" },
  { value: "zaimu_r4", label: "財務応援R4" },
];

export default function SettingsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [settings, setSettings] = useState<SettingsMap>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    getDoc(doc(getClientDb(), "users", user.uid)).then((snap) => {
      if (snap.exists()) setSettings(snap.data() as SettingsMap);
    });
  }, [user]);

  const handleSave = async () => {
    if (!user) return;
    setSaving(true);
    try {
      await setDoc(doc(getClientDb(), "users", user.uid), settings, { merge: true });
      toast.success("設定を保存しました");
    } catch (e: any) {
      toast.error(`保存に失敗しました: ${e.message}`);
    } finally {
      setSaving(false);
    }
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
      <main className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">設定</h1>

        <Card>
          <CardHeader>
            <CardTitle>基本設定</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>会社名・事業者名</Label>
              <Input
                value={String(settings.companyName ?? "")}
                onChange={(e) =>
                  setSettings({ ...settings, companyName: e.target.value })
                }
                placeholder="株式会社○○"
              />
            </div>

            <div className="space-y-2">
              <Label>会計ソフト</Label>
              <Select
                value={String(settings.accountingSoftware ?? "generic")}
                onValueChange={(v) =>
                  setSettings({ ...settings, accountingSoftware: v })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SOFTWARE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>決算月（会計年度開始月）</Label>
              <Select
                value={String(settings.fiscalYearStartMonth ?? 1)}
                onValueChange={(v) =>
                  setSettings({
                    ...settings,
                    fiscalYearStartMonth: parseInt(v ?? "1"),
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <SelectItem key={m} value={String(m)}>
                      {m}月
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Google Drive 接続</Label>
              <div className="flex items-center gap-3">
                <span
                  className={`text-sm ${
                    settings.driveConnected
                      ? "text-green-600"
                      : "text-muted-foreground"
                  }`}
                >
                  {settings.driveConnected ? "接続済み" : "未接続"}
                </span>
                {settings.driveConnected ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      await setDoc(doc(getClientDb(), "users", user.uid), {
                        driveConnected: false,
                        driveRootFolderId: "",
                        driveTempFolderId: "",
                      }, { merge: true });
                      setSettings({ ...settings, driveConnected: false, driveRootFolderId: "", driveTempFolderId: "" });
                      toast.success("Drive接続を切断しました。再接続してください。");
                    }}
                  >
                    切断して再接続
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      window.location.href = `/api/auth/drive/authorize?uid=${user?.uid || ""}`;
                    }}
                  >
                    Driveを接続
                  </Button>
                )}
              </div>
            </div>

            <Button onClick={handleSave} disabled={saving}>
              {saving ? "保存中..." : "設定を保存"}
            </Button>
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>アカウント</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              variant="outline"
              onClick={() => router.push("/setup")}
            >
              初期設定をやり直す
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                const { getAuth, signOut } = await import("firebase/auth");
                await signOut(getAuth());
                router.push("/login");
              }}
            >
              ログアウト
            </Button>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
