"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { doc, setDoc } from "firebase/firestore";
import { getClientDb } from "@/lib/firebase/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

const STEPS = ["会計ソフト選択", "基本情報", "Drive接続", "完了"];

const SOFTWARE_OPTIONS = [
  { value: "generic", label: "汎用CSV" },
  { value: "freee", label: "freee" },
  { value: "yayoi", label: "弥生会計" },
  { value: "mf", label: "MFクラウド" },
  { value: "zaimu_r4", label: "財務応援R4" },
];

export function SetupWizard() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(0);
  const [accountingSoftware, setAccountingSoftware] = useState("generic");
  const [companyName, setCompanyName] = useState("");
  const [fiscalYearStartMonth, setFiscalYearStartMonth] = useState(1);
  const [loading, setLoading] = useState(false);
  const [driveConnected, setDriveConnected] = useState(false);
  const [foldersCreated, setFoldersCreated] = useState(false);

  // Drive接続後のリダイレクトを検知 → 自動でフォルダ作成
  const folderCreationStarted = useRef(false);
  useEffect(() => {
    const driveParam = searchParams.get("drive");
    if (driveParam === "connected") {
      setDriveConnected(true);
      setStep(2);
      toast.success("Google Driveを接続しました");

      // 自動でフォルダ作成
      if (!folderCreationStarted.current && user) {
        folderCreationStarted.current = true;
        (async () => {
          setLoading(true);
          try {
            const idToken = await user.getIdToken();
            const res = await fetch("/api/drive/setup-folders", {
              method: "POST",
              headers: {
                Authorization: `Bearer ${idToken}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({ fiscalYearStartMonth }),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();

            await setDoc(
              doc(getClientDb(), "users", user.uid),
              { driveRootFolderId: data.rootFolderId },
              { merge: true }
            );

            setFoldersCreated(true);
            toast.success("Driveフォルダを作成しました");
          } catch (e: any) {
            toast.error(`フォルダ作成に失敗: ${e.message}`);
          } finally {
            setLoading(false);
          }
        })();
      }
    } else if (driveParam === "error") {
      const msg = searchParams.get("msg") || "不明なエラー";
      toast.error(`Drive接続エラー: ${decodeURIComponent(msg)}`);
      setStep(2);
    }
  }, [searchParams, user]);

  // Drive接続前に基本情報を保存
  const handleDriveConnect = async () => {
    if (user) {
      await setDoc(
        doc(getClientDb(), "users", user.uid),
        { accountingSoftware, companyName, fiscalYearStartMonth },
        { merge: true }
      );
    }
    const params = new URLSearchParams({ uid: user?.uid || "" });
    if (user?.email) params.set("email", user.email);
    window.location.href = `/api/auth/drive/authorize?${params.toString()}`;
  };

  // Firestoreから既存設定を復元
  useEffect(() => {
    if (!user) return;
    import("firebase/firestore").then(({ getDoc: gd, doc: d }) => {
      gd(d(getClientDb(), "users", user.uid)).then((snap) => {
        if (snap.exists()) {
          const data = snap.data();
          if (data.accountingSoftware) setAccountingSoftware(data.accountingSoftware);
          if (data.companyName) setCompanyName(data.companyName);
          if (data.fiscalYearStartMonth) setFiscalYearStartMonth(data.fiscalYearStartMonth);
          if (data.driveConnected) setDriveConnected(true);
        }
      });
    });
  }, [user]);

  const handleSetupFolders = async () => {
    setLoading(true);
    try {
      const idToken = await user!.getIdToken();
      const res = await fetch("/api/drive/setup-folders", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${idToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ fiscalYearStartMonth }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      // Firestoreに保存
      await setDoc(
        doc(getClientDb(), "users", user!.uid),
        { driveRootFolderId: data.rootFolderId },
        { merge: true }
      );

      setFoldersCreated(true);
      toast.success("Driveフォルダを作成しました");
      return data.rootFolderId;
    } catch (e: any) {
      toast.error(`フォルダ作成に失敗: ${e.message}`);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!user) return;
    setLoading(true);
    try {
      // 既存ユーザーはcreatedAtを上書きしない
      const userRef = doc(getClientDb(), "users", user.uid);
      const { getDoc: gd } = await import("firebase/firestore");
      const existing = await gd(userRef);
      const existingData = existing.data() || {};

      await setDoc(
        userRef,
        {
          accountingSoftware,
          companyName,
          fiscalYearStartMonth,
          ...(!existingData.createdAt && {
            createdAt: new Date().toISOString(),
            plan: "trial",
          }),
        },
        { merge: true }
      );

      // Drive接続済みだがフォルダ未作成の場合、ここで作成
      if (driveConnected && !foldersCreated) {
        const idToken = await user.getIdToken();
        const res = await fetch("/api/drive/setup-folders", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${idToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ fiscalYearStartMonth }),
        });
        if (res.ok) {
          const data = await res.json();
          await setDoc(
            doc(getClientDb(), "users", user.uid),
            { driveRootFolderId: data.rootFolderId },
            { merge: true }
          );
        }
      }

      toast.success("セットアップが完了しました");
      router.push("/dashboard");
    } catch (e: any) {
      toast.error(`保存に失敗: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Progress */}
      <div className="mb-6 flex gap-2">
        {STEPS.map((s, i) => (
          <div
            key={s}
            className={`flex-1 rounded-full py-1 text-center text-xs ${
              i <= step
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground"
            }`}
          >
            {s}
          </div>
        ))}
      </div>

      {step === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>会計ソフトを選択</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Select value={accountingSoftware} onValueChange={(v) => v && setAccountingSoftware(v)}>
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
            <Button onClick={() => setStep(1)}>次へ</Button>
          </CardContent>
        </Card>
      )}

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>基本情報</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>会社名・事業者名</Label>
              <Input
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="株式会社○○"
              />
            </div>
            <div className="space-y-2">
              <Label>会計年度開始月</Label>
              <Select
                value={String(fiscalYearStartMonth)}
                onValueChange={(v) => v && setFiscalYearStartMonth(parseInt(v))}
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
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(0)}>
                戻る
              </Button>
              <Button onClick={() => setStep(2)}>次へ</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Google Drive接続</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Drive接続状態 */}
            <div className="flex items-center gap-2">
              <span className={`text-sm font-medium ${driveConnected ? "text-green-600" : "text-muted-foreground"}`}>
                {driveConnected ? "Drive接続済み" : "未接続"}
              </span>
            </div>

            {!driveConnected && (
              <>
                <p className="text-sm text-muted-foreground">
                  領収書をGoogle Driveに保存するため、Driveへのアクセスを許可してください。
                </p>
                <Button onClick={handleDriveConnect}>Google Driveを接続</Button>
              </>
            )}

            {driveConnected && (
              <>
                {/* フォルダ作成 */}
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium ${foldersCreated ? "text-green-600" : "text-muted-foreground"}`}>
                    {foldersCreated ? "フォルダ作成済み" : "フォルダ未作成"}
                  </span>
                </div>

                {!foldersCreated && (
                  <Button onClick={handleSetupFolders} disabled={loading}>
                    {loading ? "作成中..." : "Driveフォルダを作成"}
                  </Button>
                )}
              </>
            )}

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                戻る
              </Button>
              <Button onClick={() => setStep(3)}>
                {driveConnected ? "次へ" : "スキップ（後で設定）"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle>セットアップ完了</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 text-sm">
              <p>会計ソフト: <strong>{SOFTWARE_OPTIONS.find(o => o.value === accountingSoftware)?.label}</strong></p>
              {companyName && <p>会社名: <strong>{companyName}</strong></p>}
              <p>会計年度開始: <strong>{fiscalYearStartMonth}月</strong></p>
              <p>Drive: <strong>{driveConnected ? "接続済み" : "未接続"}</strong></p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)}>
                戻る
              </Button>
              <Button onClick={handleSaveSettings} disabled={loading}>
                {loading ? "保存中..." : "設定を保存してダッシュボードへ"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
