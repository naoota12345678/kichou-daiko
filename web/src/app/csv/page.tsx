"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { exportCsv } from "@/lib/api";

function CsvPageContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const clientId = params.get("clientId") || "";
  const clientName = params.get("clientName") || "";

  const [format, setFormat] = useState<"zaimu_ouen" | "generic">("zaimu_ouen");
  const [status, setStatus] = useState<"confirmed" | "all">("confirmed");
  const [paymentMethod, setPaymentMethod] = useState<"" | "現金" | "カード">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [preview, setPreview] = useState("");

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

  if (!clientId) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="mx-auto max-w-3xl px-4 py-8">
          <p className="text-muted-foreground">ダッシュボードから顧問先を選択してください。</p>
          <button onClick={() => router.push("/dashboard")} className="mt-4 text-sm underline">ダッシュボードへ戻る</button>
        </main>
      </div>
    );
  }

  const handlePreview = async () => {
    try {
      const { text } = await exportCsv(clientId, format, status, paymentMethod, dateFrom, dateTo);
      setPreview(text);
    } catch (e: any) {
      setPreview(`エラー: ${e.message}`);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const { blob } = await exportCsv(clientId, format, status, paymentMethod, dateFrom, dateTo);
      const filename = format === "zaimu_ouen" ? "zaimu_ouen_import.csv" : "journal_entries.csv";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(`ダウンロード失敗: ${e.message}`);
    } finally {
      setDownloading(false);
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
          <h1 className="text-2xl font-bold">CSV出力</h1>
        </div>
        <p className="text-sm text-muted-foreground mb-6">顧問先: <strong>{clientName}</strong></p>

        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">出力形式</label>
              <select value={format} onChange={(e) => setFormat(e.target.value as any)} className="w-full p-2 border rounded text-sm">
                <option value="zaimu_ouen">財務応援R4</option>
                <option value="generic">汎用CSV（根拠付き）</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">ステータス</label>
              <select value={status} onChange={(e) => setStatus(e.target.value as any)} className="w-full p-2 border rounded text-sm">
                <option value="confirmed">確定済のみ</option>
                <option value="all">全件</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">支払方法</label>
              <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value as any)} className="w-full p-2 border rounded text-sm">
                <option value="">全て</option>
                <option value="現金">現金</option>
                <option value="カード">カード</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">アップロード日（開始）</label>
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full p-2 border rounded text-sm" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">アップロード日（終了）</label>
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full p-2 border rounded text-sm" />
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={handlePreview} className="px-4 py-2 bg-gray-100 rounded text-sm hover:bg-gray-200">
              プレビュー
            </button>
            <button onClick={handleDownload} disabled={downloading} className="px-4 py-2 bg-black text-white rounded text-sm disabled:opacity-50">
              {downloading ? "ダウンロード中..." : "CSVダウンロード"}
            </button>
          </div>
        </div>

        {preview && (
          <div className="bg-white rounded-lg shadow-sm p-4">
            <h2 className="font-bold text-sm mb-2">プレビュー</h2>
            <pre className="text-xs overflow-x-auto whitespace-pre bg-gray-50 p-3 rounded max-h-96 overflow-y-auto">{preview}</pre>
          </div>
        )}
      </main>
    </div>
  );
}

export default function CsvPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><p className="text-muted-foreground">読み込み中...</p></div>}>
      <CsvPageContent />
    </Suspense>
  );
}
