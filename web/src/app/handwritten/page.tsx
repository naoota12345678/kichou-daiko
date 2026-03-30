"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { uploadReceipt, processAllUploaded, listReceipts, getInstructions, updateInstructions, deleteErrorReceipts } from "@/lib/api";
import Link from "next/link";

function HandwrittenPageContent() {
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
  const [instructions, setInstructions] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Firestoreから指示を読み込み
  useEffect(() => {
    if (clientId && user) {
      getInstructions(clientId).then((data) => {
        if (data.instructions) setInstructions(data.instructions);
      }).catch(() => {});
    }
  }, [clientId, user]);

  // 指示が変更されたらFirestoreに保存（デバウンス）
  const saveTimerRef = useRef<any>(null);
  const handleInstructionsChange = (value: string) => {
    setInstructions(value);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      if (clientId) updateInstructions(clientId, value).catch(() => {});
    }, 1000);
  };

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const loadPendingCount = async () => {
    if (!clientId || !user) return;
    try {
      const data = await listReceipts(clientId);
      const uploaded = (data.receipts || []).filter(
        (r: any) => r.status === "uploaded" && r.receiptType === "handwritten"
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

    for (let i = 0; i < files.length; i++) {
      setUploadedCount(i + 1);
      try {
        await uploadReceipt(files[i], clientId, "handwritten", instructions);
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
    processAllUploaded(clientId, "handwritten")
      .then((result) => {
        setProcessResult(result);
        setProcessing(false);
        loadPendingCount();
      })
      .catch(() => {});

    const poll = setInterval(async () => {
      try {
        const data = await listReceipts(clientId);
        const remaining = (data.receipts || []).filter(
          (r: any) => r.status === "uploaded" && r.receiptType === "handwritten"
        );
        setPendingCount(remaining.length);
        if (remaining.length === 0) {
          clearInterval(poll);
          setProcessing(false);
          loadPendingCount();
        }
      } catch {}
    }, 5000);

    setTimeout(() => clearInterval(poll), 600000);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => router.push("/dashboard")} className="text-sm text-muted-foreground hover:underline">
            ← 戻る
          </button>
          <h1 className="text-2xl font-bold">手書き領収書</h1>
        </div>
        <p className="text-sm text-muted-foreground mb-4">顧問先: <strong>{clientName}</strong></p>

        {/* 追加指示 */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-4">
          <h2 className="font-bold text-base mb-2">仕訳の追加指示</h2>
          <p className="text-xs text-muted-foreground mb-2">
            この顧問先の手書き領収書に対する指示を入力してください。AIの仕訳判定に反映されます。
          </p>
          <textarea
            value={instructions}
            onChange={(e) => handleInstructionsChange(e.target.value)}
            placeholder={"例:\n・相手科目は売掛金にする\n・飲食店からの領収書は交際費\n・10万円以上は備品として資産計上"}
            rows={4}
            className="w-full p-3 border rounded text-sm resize-y"
          />
        </div>

        {/* ステップ1: アップロード */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-4">
          <h2 className="font-bold text-base mb-3">① 領収書を撮影・選択</h2>
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

        {/* ステップ2: 一括処理 */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-4">
          <h2 className="font-bold text-base mb-3">② まとめて仕訳処理</h2>
          <p className="text-sm text-muted-foreground mb-3">
            未処理の領収書: <strong>{pendingCount}件</strong>
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
                      {r.fileName && <span className="text-muted-foreground mr-2">{r.fileName}:</span>}
                      {r.vendor} ¥{r.amount?.toLocaleString()}
                      {r.entries > 1 && <span className="ml-2 text-xs text-blue-600">税率分割{r.entries}行</span>}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-4">
              <Link
                href={`/journals?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`}
                className="inline-block px-4 py-2 bg-black text-white rounded text-sm"
              >
                仕訳一覧を確認 →
              </Link>
              {processResult.results?.some((r: any) => r.error) && (
                <button
                  onClick={async () => {
                    if (!confirm("エラーのレシートをまとめて削除しますか？")) return;
                    try {
                      const res = await deleteErrorReceipts(clientId);
                      alert(`${res.deleted}件のエラーレシートを削除しました`);
                      setProcessResult(null);
                      await loadPendingCount();
                    } catch (e: any) {
                      alert(`削除失敗: ${e.message}`);
                    }
                  }}
                  className="px-4 py-2 bg-red-600 text-white rounded text-sm"
                >
                  エラー分を削除
                </button>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function HandwrittenPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><p className="text-muted-foreground">読み込み中...</p></div>}>
      <HandwrittenPageContent />
    </Suspense>
  );
}
