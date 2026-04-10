"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { uploadReceipt, processAllUploaded, listReceipts, importFromDrive } from "@/lib/api";
import Link from "next/link";

function ReceiptsPageContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const clientId = params.get("clientId") || "";
  const clientName = params.get("clientName") || "";

  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [processResult, setProcessResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // 未処理レシート数を取得
  const loadPendingCount = async () => {
    if (!clientId || !user) return;
    try {
      const data = await listReceipts(clientId);
      const uploaded = (data.receipts || []).filter(
        (r: any) => r.status === "uploaded" && (r.receiptType || "receipt") === "receipt"
      );
      setPendingCount(uploaded.length);
    } catch {}
  };

  useEffect(() => {
    loadPendingCount();
  }, [user, clientId]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  if (!clientId) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="mx-auto max-w-3xl px-4 py-8">
          <p className="text-muted-foreground">ダッシュボードから顧問先を選択してください。</p>
          <button onClick={() => router.push("/dashboard")} className="mt-4 text-sm underline">
            ダッシュボードへ戻る
          </button>
        </main>
      </div>
    );
  }

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
      setError("");
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError("");
    let count = 0;

    for (let i = 0; i < files.length; i++) {
      setUploadedCount(i + 1);
      try {
        await uploadReceipt(files[i], clientId);
        count++;
      } catch (e: any) {
        setError(`${files[i].name}: ${e.message}`);
      }
    }

    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setUploading(false);
    setUploadedCount(0);
    await loadPendingCount();
  };

  const handleProcessAll = async () => {
    setProcessing(true);
    setProcessResult(null);
    setError("");
    // サーバーにリクエストを投げて、レスポンスを待たない
    processAllUploaded(clientId, "receipt")
      .then((result) => {
        setProcessResult(result);
        setProcessing(false);
        loadPendingCount();
      })
      .catch(() => {
        // タイムアウトしても処理は続いている可能性あり
      });

    // ポーリングで進捗確認（5秒ごと）
    const poll = setInterval(async () => {
      try {
        const data = await listReceipts(clientId);
        const remaining = (data.receipts || []).filter(
          (r: any) => r.status === "uploaded" && (r.receiptType || "receipt") === "receipt"
        );
        setPendingCount(remaining.length);
        if (remaining.length === 0) {
          clearInterval(poll);
          setProcessing(false);
          loadPendingCount();
        }
      } catch {}
    }, 5000);

    // 10分でポーリング停止
    setTimeout(() => clearInterval(poll), 600000);
  };

  const handleImportFromDrive = async () => {
    setImporting(true);
    setImportResult(null);
    setError("");
    try {
      const result = await importFromDrive(clientId);
      setImportResult(result);
      await loadPendingCount();
    } catch (e: any) {
      setError(`Drive取込エラー: ${e.message}`);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => router.push("/dashboard")} className="text-sm text-muted-foreground hover:underline">
            ← 戻る
          </button>
          <h1 className="text-2xl font-bold">レシートアップロード</h1>
        </div>
        <p className="text-sm text-muted-foreground mb-4">顧問先: <strong>{clientName}</strong></p>

        {/* ステップ1: アップロード */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-4">
          <h2 className="font-bold text-base mb-3">① レシートを選択・アップロード</h2>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/heic,image/heif,application/pdf"
            multiple
            onChange={handleFiles}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-full py-4 border-2 border-dashed border-gray-300 rounded-lg text-sm text-muted-foreground hover:border-gray-500 hover:bg-gray-50 transition mb-3"
          >
            写真を選択 / カメラで撮影
          </button>

          {files.length > 0 && (
            <div className="mb-3">
              <p className="text-sm text-muted-foreground mb-2">{files.length}件選択中</p>
              <ul className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                {files.map((f, i) => (
                  <li key={i}>{f.name} ({Math.round(f.size / 1024)}KB)</li>
                ))}
              </ul>
            </div>
          )}

          <button
            onClick={handleUpload}
            disabled={files.length === 0 || uploading}
            className="w-full py-3 bg-black text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {uploading
              ? `アップロード中... (${uploadedCount}/${files.length})`
              : `アップロード (${files.length}件)`}
          </button>
        </div>

        {/* Driveから取り込み */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-4">
          <h2 className="font-bold text-base mb-3">Driveから取り込み</h2>
          <p className="text-xs text-muted-foreground mb-3">
            Google Driveの「{clientName}」フォルダ内の画像を自動で取り込みます。
            既に取り込み済みのファイルはスキップされます。
          </p>
          <button
            onClick={handleImportFromDrive}
            disabled={importing}
            className="w-full py-3 bg-blue-600 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {importing ? "取り込み中..." : "Driveから画像を取り込み"}
          </button>
          {importResult && (
            <p className="text-sm mt-2 text-green-700">
              {importResult.message}
            </p>
          )}
        </div>

        {/* ステップ2: 一括処理 */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-4">
          <h2 className="font-bold text-base mb-3">② まとめて仕訳処理</h2>
          <p className="text-sm text-muted-foreground mb-3">
            未処理のレシート: <strong>{pendingCount}件</strong>
          </p>
          <button
            onClick={handleProcessAll}
            disabled={pendingCount === 0 || processing}
            className="w-full py-3 bg-green-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {processing
              ? `処理中... 残り${pendingCount}件`
              : `${pendingCount}件を一括処理（OCR→仕訳）`}
          </button>
        </div>

        {error && (
          <div className="bg-red-50 rounded-lg p-4 mb-4">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {processResult && (
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="font-bold text-base mb-3">処理結果: {processResult.processed}件</h2>
            <div className="space-y-2">
              {processResult.results?.map((r: any, i: number) => (
                <div key={i} className="text-sm py-2 px-3 rounded bg-gray-50">
                  {r.error ? (
                    <p className="text-red-600">{r.fileName || r.receiptId}: {r.error}</p>
                  ) : (
                    <p>
                      {r.vendor} ¥{r.amount?.toLocaleString()}
                      {r.entries > 1 && <span className="ml-2 text-xs text-blue-600">税率分割{r.entries}行</span>}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <Link
              href={`/journals?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}
              className="inline-block mt-4 px-4 py-2 bg-black text-white rounded text-sm"
            >
              仕訳一覧を確認 →
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}

export default function ReceiptsPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><p className="text-muted-foreground">読み込み中...</p></div>}>
      <ReceiptsPageContent />
    </Suspense>
  );
}
