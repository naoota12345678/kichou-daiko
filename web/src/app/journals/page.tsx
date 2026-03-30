"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { listReceipts, updateJournal, confirmJournal, deleteReceipt } from "@/lib/api";

interface Receipt {
  id: string;
  vendor: string;
  amount: number;
  date: string;
  paymentMethod: string;
  status: string;
  journal: {
    debitAccount: string;
    debitCode: string;
    creditAccount: string;
    creditCode: string;
    taxRate: string;
    description: string;
    vendor: string;
    confidence: string;
    reasoning: string;
  };
}

function JournalsPageContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const clientId = params.get("clientId") || "";
  const clientName = params.get("clientName") || "";

  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<any>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const loadData = async () => {
    if (!clientId) return;
    setLoadingData(true);
    try {
      const data = await listReceipts(clientId);
      const all = data.receipts || [];
      setReceipts(all.filter((r: Receipt) => r.status !== "confirmed" && r.journal));
    } catch (e) {
      console.error("Failed to load receipts:", e);
    } finally {
      setLoadingData(false);
    }
  };

  useEffect(() => {
    if (user && clientId) loadData();
  }, [user, clientId]);

  const pendingReceipts = receipts.filter((r) => r.status !== "confirmed");

  const handleSelectAll = () => {
    if (selected.size === receipts.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(receipts.map((r) => r.id)));
    }
  };

  const handleToggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const handleConfirm = async (receiptId: string) => {
    try {
      await confirmJournal(clientId, receiptId);
      await loadData();
    } catch (e) {
      console.error("Failed to confirm:", e);
    }
  };

  const handleBulkConfirm = async () => {
    const pending = [...selected].filter((id) => {
      const r = receipts.find((r) => r.id === id);
      return r && r.status !== "confirmed";
    });
    if (pending.length === 0) return;
    setConfirming(true);
    try {
      for (const id of pending) {
        await confirmJournal(clientId, id);
      }
      setSelected(new Set());
      await loadData();
    } catch (e) {
      console.error("Failed to bulk confirm:", e);
    } finally {
      setConfirming(false);
    }
  };

  const [deleting, setDeleting] = useState(false);

  const handleBulkDelete = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`${selected.size}件の仕訳を削除しますか？この操作は取り消せません。`)) return;
    setDeleting(true);
    try {
      for (const id of selected) {
        await deleteReceipt(clientId, id);
      }
      setSelected(new Set());
      await loadData();
    } catch (e) {
      console.error("Failed to bulk delete:", e);
    } finally {
      setDeleting(false);
    }
  };

  const handleEdit = (r: Receipt) => {
    setEditingId(r.id);
    setEditData({
      debit_account: r.journal.debitAccount,
      debit_code: r.journal.debitCode,
      credit_account: r.journal.creditAccount,
      credit_code: r.journal.creditCode,
      tax_rate: r.journal.taxRate,
      description: r.journal.description,
      vendor: r.journal.vendor,
      amount: r.amount,
    });
  };

  const handleSave = async () => {
    if (!editingId) return;
    try {
      await updateJournal(clientId, editingId, editData);
      setEditingId(null);
      await loadData();
    } catch (e) {
      console.error("Failed to update:", e);
    }
  };

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

  const statusLabel = (s: string) => {
    if (s === "confirmed") return "確定";
    if (s === "edited") return "修正済";
    return "未確定";
  };

  const statusColor = (s: string) => {
    if (s === "confirmed") return "text-green-600";
    if (s === "edited") return "text-blue-600";
    return "text-orange-600";
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-4xl px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => router.push("/dashboard")} className="text-sm text-muted-foreground hover:underline">
            ← 戻る
          </button>
          <h1 className="text-2xl font-bold">仕訳一覧</h1>
        </div>
        <p className="text-sm text-muted-foreground mb-4">顧問先: <strong>{clientName}</strong></p>

        {loadingData ? (
          <p className="text-muted-foreground">読み込み中...</p>
        ) : receipts.length === 0 ? (
          <p className="text-muted-foreground bg-white rounded-lg shadow-sm p-6">仕訳データがありません。レシートをアップロードしてください。</p>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4 bg-white rounded-lg shadow-sm p-3 flex-wrap">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.size === receipts.length && receipts.length > 0}
                  onChange={handleSelectAll}
                  className="w-4 h-4"
                />
                全選択 ({selected.size}/{receipts.length}件)
              </label>
              {pendingReceipts.length > 0 && (
                <button
                  onClick={handleBulkConfirm}
                  disabled={selected.size === 0 || confirming}
                  className="px-4 py-2 bg-green-700 text-white rounded text-sm disabled:opacity-50"
                >
                  {confirming ? `確定中...` : `一括確定`}
                </button>
              )}
              <button
                onClick={handleBulkDelete}
                disabled={selected.size === 0 || deleting}
                className="px-4 py-2 bg-red-600 text-white rounded text-sm disabled:opacity-50"
              >
                {deleting ? `削除中...` : `一括削除`}
              </button>
            </div>

          <div className="space-y-3">
            {receipts.map((r) => (
              <div key={r.id} className="bg-white rounded-lg shadow-sm p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => handleToggle(r.id)}
                      className="w-4 h-4 shrink-0"
                    />
                    <span className="text-sm font-medium">{r.date}</span>
                    <span className="ml-2 text-sm">{r.vendor}</span>
                    <span className="ml-2 text-sm font-bold">¥{r.amount?.toLocaleString()}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{r.paymentMethod}</span>
                  </div>
                  <span className={`text-xs font-medium ${statusColor(r.status)}`}>
                    {statusLabel(r.status)}
                  </span>
                </div>

                {editingId === r.id ? (
                  <div className="space-y-2 mt-3 border-t pt-3">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-xs text-muted-foreground">借方科目</label>
                        <input value={editData.debit_account} onChange={(e) => setEditData({ ...editData, debit_account: e.target.value })} className="w-full p-2 border rounded text-sm" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">貸方科目</label>
                        <input value={editData.credit_account} onChange={(e) => setEditData({ ...editData, credit_account: e.target.value })} className="w-full p-2 border rounded text-sm" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">借方コード</label>
                        <input value={editData.debit_code} onChange={(e) => setEditData({ ...editData, debit_code: e.target.value })} className="w-full p-2 border rounded text-sm" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">貸方コード</label>
                        <input value={editData.credit_code} onChange={(e) => setEditData({ ...editData, credit_code: e.target.value })} className="w-full p-2 border rounded text-sm" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">税率</label>
                        <input value={editData.tax_rate} onChange={(e) => setEditData({ ...editData, tax_rate: e.target.value })} className="w-full p-2 border rounded text-sm" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">金額</label>
                        <input type="number" value={editData.amount} onChange={(e) => setEditData({ ...editData, amount: parseInt(e.target.value) || 0 })} className="w-full p-2 border rounded text-sm" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">取引先</label>
                        <input value={editData.vendor} onChange={(e) => setEditData({ ...editData, vendor: e.target.value })} className="w-full p-2 border rounded text-sm" />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">摘要</label>
                      <input value={editData.description} onChange={(e) => setEditData({ ...editData, description: e.target.value })} className="w-full p-2 border rounded text-sm" />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleSave} className="px-4 py-2 bg-black text-white rounded text-sm">保存</button>
                      <button onClick={() => setEditingId(null)} className="px-4 py-2 text-sm text-muted-foreground">キャンセル</button>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm">
                    <p className="text-muted-foreground">
                      {r.journal.debitAccount}({r.journal.debitCode}) / {r.journal.creditAccount}({r.journal.creditCode})
                      {r.journal.confidence === "low" && <span className="ml-1 text-orange-600">要確認</span>}
                    </p>
                    <p className="text-xs text-muted-foreground">{r.journal.description}</p>
                    {r.journal.reasoning && (
                      <p className="text-xs text-muted-foreground mt-1">根拠: {r.journal.reasoning}</p>
                    )}
                    <div className="flex gap-2 mt-2">
                      <button onClick={() => handleEdit(r)} className="text-xs underline text-muted-foreground">修正</button>
                      {r.status !== "confirmed" && (
                        <button onClick={() => handleConfirm(r.id)} className="text-xs underline text-green-700">確定</button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          </>
        )}
      </main>
    </div>
  );
}

export default function JournalsPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><p className="text-muted-foreground">読み込み中...</p></div>}>
      <JournalsPageContent />
    </Suspense>
  );
}
