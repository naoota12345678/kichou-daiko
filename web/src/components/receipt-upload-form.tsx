"use client";

import { useState, useRef, useEffect } from "react";
import { collection, onSnapshot, query, orderBy, limit } from "firebase/firestore";
import { getClientDb } from "@/lib/firebase/client";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

type ReceiptType = "カード" | "現金";

interface UploadedFile {
  name: string;
  status: "uploading" | "done" | "error";
  path?: string;
}

export function ReceiptUploadForm() {
  const { user } = useAuth();
  const [receiptType, setReceiptType] = useState<ReceiptType>("現金");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  const uploadFile = async (file: File) => {
    if (!user) return;

    const fileName = file.name || `receipt_${Date.now()}.jpg`;
    setFiles((prev) => [...prev, { name: fileName, status: "uploading" }]);

    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const idToken = await user.getIdToken();
        const formData = new FormData();
        formData.append("file", file);
        formData.append("receiptType", receiptType);

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);

        const res = await fetch("/api/drive/upload-quick", {
          method: "POST",
          headers: { Authorization: `Bearer ${idToken}` },
          body: formData,
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();

        setFiles((prev) =>
          prev.map((f) => (f.name === fileName ? { ...f, status: "done", path: data.path } : f))
        );
        return;
      } catch (e: any) {
        if (attempt === 1) {
          setFiles((prev) =>
            prev.map((f) => (f.name === fileName ? { ...f, status: "error" } : f))
          );
          toast.error(`${fileName}: ${e.message || "アップロード失敗"}`);
        }
      }
    }
  };

  const activeUploads = useRef(0);

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files;
    if (!selected || selected.length === 0) return;

    // inputを即リセット（同じファイルの再選択を可能にする）
    const rawList = Array.from(selected);
    if (inputRef.current) inputRef.current.value = "";
    if (cameraRef.current) cameraRef.current.value = "";

    // ファイル名+サイズで重複排除
    const seen = new Set<string>();
    const fileList = rawList.filter((f) => {
      const key = `${f.name}_${f.size}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (fileList.length === 0) return;

    setUploading(true);

    // Cloud Runウォームアップ（バックグラウンド、初回のみ）
    if (SCRAPER_API_URL && activeUploads.current === 0) {
      fetch(`${SCRAPER_API_URL}/api/warmup`, { method: "POST" }).catch(() => {});
    }

    activeUploads.current += fileList.length;

    // 3件ずつ並列アップロード
    for (let i = 0; i < fileList.length; i += 3) {
      const batch = fileList.slice(i, i + 3);
      await Promise.all(batch.map((f) => uploadFile(f)));
    }

    activeUploads.current -= fileList.length;
    if (activeUploads.current <= 0) {
      activeUploads.current = 0;
      setUploading(false);
    }

    toast.success(`${fileList.length}件をDriveに保存しました`);
  };

  const [processing, setProcessing] = useState(false);
  const [processResults, setProcessResults] = useState<any[]>([]);

  const SCRAPER_API_URL = process.env.NEXT_PUBLIC_SCRAPER_API_URL || "";

  const handleProcess = async () => {
    if (!user || !SCRAPER_API_URL) return;
    processStartTime.current = Date.now();
    setProcessing(true);
    setProcessResults([]);
    try {
      const idToken = await user.getIdToken();
      const res = await fetch(`${SCRAPER_API_URL}/api/process-receipts`, {
        method: "POST",
        headers: { Authorization: `Bearer ${idToken}` },
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText);
      }

      toast.success("処理を開始しました。このページを閉じても大丈夫です。");
    } catch (e: any) {
      toast.error(`処理開始に失敗: ${e.message}`);
      setProcessing(false);
    }
  };

  // Firestoreでジョブ結果を監視
  const processStartTime = useRef<number>(0);
  useEffect(() => {
    if (!user || !processing) return;

    const db = getClientDb();
    const jobsRef = collection(db, "users", user.uid, "receipt_jobs");
    const q = query(jobsRef, orderBy("createdAt", "desc"), limit(1));

    const unsub = onSnapshot(q, (snapshot) => {
      snapshot.forEach((doc) => {
        const data = doc.data();
        // 処理開始前のジョブは無視
        const jobTime = data.createdAt?.toMillis?.() || 0;
        if (jobTime < processStartTime.current - 5000) return;

        if (data.status === "complete" && data.results?.length > 0) {
          setProcessResults(data.results);
          setProcessing(false);
          toast.success(`${data.results.length}件処理しました`);
        } else if (data.status === "processing") {
          setProcessResults(data.results || []);
        }
      });
    });

    return unsub;
  }, [user, processing]);

  const doneCount = files.filter((f) => f.status === "done").length;
  const uploadingCount = files.filter((f) => f.status === "uploading").length;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>レシート保存</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-2">
            <label className="flex h-16 cursor-pointer items-center justify-center rounded-md border-2 border-dashed bg-gray-50 text-sm font-medium hover:bg-gray-100">
              📷 撮影
              <input
                ref={cameraRef}
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handleFiles}
                className="hidden"
              />
            </label>
            <label className="flex h-16 cursor-pointer items-center justify-center rounded-md border-2 border-dashed bg-gray-50 text-sm font-medium hover:bg-gray-100">
              📁 まとめて選択
              <input
                ref={inputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={handleFiles}
                className="hidden"
              />
            </label>
          </div>

          {uploading && (
            <p className="text-sm text-center text-muted-foreground">
              アップロード中... ({uploadingCount}件)
            </p>
          )}

          <Button
            onClick={handleProcess}
            disabled={processing || uploading}
            variant="secondary"
            className="w-full h-12"
          >
            {processing ? `処理中... (${processResults.length}件完了)` : uploading ? "アップロード完了後に押してください" : "まとめて読み取り処理"}
          </Button>

          {processing && (
            <p className="text-xs text-center text-muted-foreground">
              このページを閉じても処理は続きます
            </p>
          )}

          <div className="rounded-md bg-gray-50 p-3 text-xs text-muted-foreground">
            <p>1. レシートを撮影 → Driveに即保存</p>
            <p>2.「まとめて読み取り処理」→ 金額・T番号・現金/カードを自動判定</p>
            <p className="mt-1 font-medium">※ 対応形式: JPEG・PNG（PDFは不可）</p>
          </div>
        </CardContent>
      </Card>

      {processResults.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">読み取り結果</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {processResults.map((r, i) => (
              <div key={i} className="text-xs border-b pb-1">
                {r.error ? (
                  <p className="text-red-500">{r.oldName}: {r.error}</p>
                ) : (
                  <p className={r.confidence === "low" ? "text-red-500" : "text-muted-foreground"}>
                    {r.confidence === "low" && <span className="font-bold mr-1">⚠要確認</span>}
                    {r.newName} <span className="text-green-600">¥{Number(r.amount).toLocaleString()}</span>
                    {r.invoiceNumber && <span className="ml-1 text-blue-600">{r.invoiceNumber}</span>}
                    <span className="ml-1">{r.paymentMethod === "カード" ? "💳" : "💴"}</span>
                  </p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {files.length > 0 && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm font-medium text-green-700 mb-1">
              {doneCount}件保存済み
            </p>
            {files.find((f) => f.path) && (
              <p className="text-xs text-muted-foreground mb-2">
                保存先: Google Drive / {files.find((f) => f.path)?.path}
              </p>
            )}
            <ul className="space-y-1">
              {files.map((f, i) => (
                <li key={i} className="flex items-center gap-2 text-xs">
                  <span>
                    {f.status === "done" ? "✓" : f.status === "uploading" ? "⏳" : "✗"}
                  </span>
                  <span className={`truncate ${f.status === "error" ? "text-red-500" : "text-muted-foreground"}`}>
                    {f.name}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
