"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import {
  listPatterns, createPattern, deletePattern,
  listRules, createRule, deleteRule,
  listCustomers, createCustomer, deleteCustomer, deleteAllCustomers,
} from "@/lib/api";

interface Pattern {
  id: string;
  keywords: string[];
  vendorName: string;
  debitAccount: string;
  debitCode: string;
  creditAccount: string;
  creditCode: string;
  taxRate: string;
  taxCategory: string;
  descriptionTemplate: string;
}

interface Rule {
  id: string;
  text: string;
}

function RulesPageContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const clientId = params.get("clientId") || "";
  const clientName = params.get("clientName") || "";

  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [newRule, setNewRule] = useState("");
  const [customers, setCustomers] = useState<any[]>([]);
  const [showCustomerForm, setShowCustomerForm] = useState(false);
  const [customerForm, setCustomerForm] = useState({ name: "", code: "", account: "売掛金", account_code: "" });
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvProgress, setCsvProgress] = useState("");
  const [showPatternForm, setShowPatternForm] = useState(false);
  const [patternForm, setPatternForm] = useState({
    keywords: "",
    vendor_name: "",
    debit_account: "",
    debit_code: "",
    credit_account: "",
    credit_code: "",
    tax_rate: "10",
    tax_category: "",
    description_template: "",
  });

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const loadData = async () => {
    if (!clientId) return;
    try {
      const [pData, rData, cData] = await Promise.all([
        listPatterns(clientId),
        listRules(clientId),
        listCustomers(clientId),
      ]);
      setPatterns(pData.patterns || []);
      setRules(rData.rules || []);
      setCustomers(cData.customers || []);
    } catch (e) {
      console.error("Failed to load:", e);
    }
  };

  useEffect(() => {
    if (user && clientId) loadData();
  }, [user, clientId]);

  const handleAddRule = async () => {
    if (!newRule.trim()) return;
    try {
      await createRule(clientId, newRule.trim());
      setNewRule("");
      await loadData();
    } catch (e) {
      console.error("Failed to add rule:", e);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await deleteRule(clientId, ruleId);
      await loadData();
    } catch (e) {
      console.error("Failed to delete rule:", e);
    }
  };

  const handleAddPattern = async () => {
    if (!patternForm.debit_account || !patternForm.credit_account) return;
    try {
      await createPattern(clientId, {
        keywords: patternForm.keywords.split(",").map((k) => k.trim()).filter(Boolean),
        vendor_name: patternForm.vendor_name,
        debit_account: patternForm.debit_account,
        debit_code: patternForm.debit_code,
        credit_account: patternForm.credit_account,
        credit_code: patternForm.credit_code,
        tax_rate: patternForm.tax_rate,
        tax_category: patternForm.tax_category,
        description_template: patternForm.description_template,
      });
      setPatternForm({
        keywords: "", vendor_name: "", debit_account: "", debit_code: "",
        credit_account: "", credit_code: "", tax_rate: "10", tax_category: "",
        description_template: "",
      });
      setShowPatternForm(false);
      await loadData();
    } catch (e) {
      console.error("Failed to add pattern:", e);
    }
  };

  const handleDeletePattern = async (patternId: string) => {
    try {
      await deletePattern(clientId, patternId);
      await loadData();
    } catch (e) {
      console.error("Failed to delete pattern:", e);
    }
  };

  const handleRuleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleAddRule();
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

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => router.push("/dashboard")} className="text-sm text-muted-foreground hover:underline">
            ← 戻る
          </button>
          <h1 className="text-2xl font-bold">仕訳ルール管理</h1>
        </div>
        <p className="text-sm text-muted-foreground mb-6">顧問先: <strong>{clientName}</strong></p>

        {/* テキストルール */}
        <div className="bg-white rounded-lg shadow-sm p-4 mb-6">
          <h2 className="font-bold text-base mb-2">追加ルール（AIプロンプトに反映）</h2>
          <p className="text-xs text-muted-foreground mb-3">
            自然文でルールを追加できます。レシート処理時にAIが参照します。
          </p>

          <div className="flex gap-2 mb-3">
            <input
              placeholder="例: ドラッグストアでの購入は全て消耗品費760"
              value={newRule}
              onChange={(e) => setNewRule(e.target.value)}
              onKeyDown={handleRuleKeyDown}
              className="flex-1 p-2 border rounded text-sm"
            />
            <button onClick={handleAddRule} disabled={!newRule.trim()} className="px-4 py-2 bg-black text-white rounded text-sm disabled:opacity-50">
              追加
            </button>
          </div>

          {rules.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">ルールが登録されていません</p>
          ) : (
            <ul className="space-y-1">
              {rules.map((rule, i) => (
                <li key={rule.id} className="flex items-start gap-2 text-sm py-2 px-3 rounded bg-gray-50">
                  <span className="text-muted-foreground shrink-0">{i + 1}.</span>
                  <span className="flex-1">{rule.text}</span>
                  <button onClick={() => handleDeleteRule(rule.id)} className="text-muted-foreground hover:text-red-500 shrink-0 px-1">
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 仕訳パターン */}
        <div className="bg-white rounded-lg shadow-sm p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-bold text-base">仕訳パターンマスタ</h2>
            <button
              onClick={() => setShowPatternForm(!showPatternForm)}
              className="text-sm px-3 py-1 bg-gray-100 rounded hover:bg-gray-200"
            >
              {showPatternForm ? "閉じる" : "+ 追加"}
            </button>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            キーワードに基づいて自動的に勘定科目を割り当てます。
          </p>

          {showPatternForm && (
            <div className="border rounded p-3 mb-4 space-y-2">
              <div>
                <label className="text-xs text-muted-foreground">キーワード（カンマ区切り）</label>
                <input value={patternForm.keywords} onChange={(e) => setPatternForm({ ...patternForm, keywords: e.target.value })} placeholder="例: ツルハ, ドラッグストア" className="w-full p-2 border rounded text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">借方科目</label>
                  <input value={patternForm.debit_account} onChange={(e) => setPatternForm({ ...patternForm, debit_account: e.target.value })} placeholder="消耗品費" className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">借方コード</label>
                  <input value={patternForm.debit_code} onChange={(e) => setPatternForm({ ...patternForm, debit_code: e.target.value })} placeholder="760" className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">貸方科目</label>
                  <input value={patternForm.credit_account} onChange={(e) => setPatternForm({ ...patternForm, credit_account: e.target.value })} placeholder="現金" className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">貸方コード</label>
                  <input value={patternForm.credit_code} onChange={(e) => setPatternForm({ ...patternForm, credit_code: e.target.value })} placeholder="100" className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">税率</label>
                  <input value={patternForm.tax_rate} onChange={(e) => setPatternForm({ ...patternForm, tax_rate: e.target.value })} className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">税区分</label>
                  <input value={patternForm.tax_category} onChange={(e) => setPatternForm({ ...patternForm, tax_category: e.target.value })} placeholder="課税仕入10%" className="w-full p-2 border rounded text-sm" />
                </div>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">取引先名</label>
                <input value={patternForm.vendor_name} onChange={(e) => setPatternForm({ ...patternForm, vendor_name: e.target.value })} className="w-full p-2 border rounded text-sm" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">摘要テンプレート</label>
                <input value={patternForm.description_template} onChange={(e) => setPatternForm({ ...patternForm, description_template: e.target.value })} className="w-full p-2 border rounded text-sm" />
              </div>
              <button onClick={handleAddPattern} disabled={!patternForm.debit_account || !patternForm.credit_account} className="px-4 py-2 bg-black text-white rounded text-sm disabled:opacity-50">
                パターン登録
              </button>
            </div>
          )}

          {patterns.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">パターンが登録されていません</p>
          ) : (
            <div className="space-y-2">
              {patterns.map((p) => (
                <div key={p.id} className="flex items-start gap-2 text-sm py-2 px-3 rounded bg-gray-50">
                  <div className="flex-1">
                    <p className="font-medium">{p.keywords?.join(", ")}</p>
                    <p className="text-xs text-muted-foreground">
                      {p.debitAccount}({p.debitCode}) / {p.creditAccount}({p.creditCode}) 税率{p.taxRate}%
                      {p.vendorName && ` 取引先:${p.vendorName}`}
                    </p>
                  </div>
                  <button onClick={() => handleDeletePattern(p.id)} className="text-muted-foreground hover:text-red-500 shrink-0 px-1">
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 得意先マスタ */}
        <div className="bg-white rounded-lg shadow-sm p-4 mt-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-bold text-base">得意先マスタ</h2>
            <div className="flex gap-2">
              <button
                onClick={() => setShowCustomerForm(!showCustomerForm)}
                className="text-sm px-3 py-1 bg-gray-100 rounded hover:bg-gray-200"
              >
                {showCustomerForm ? "閉じる" : "+ 追加"}
              </button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            手書き領収書の取引先照合に使います。マスタに当てはまらない場合、補助科目は「その他」になります。
          </p>

          {/* CSV一括取り込み */}
          <div className="border rounded p-3 mb-4">
            <p className="text-xs font-medium mb-1">CSV一括取り込み</p>
            <p className="text-xs text-muted-foreground mb-2">
              形式: 得意先名,補助コード,勘定科目,科目コード（1行1件、ヘッダー行不要）
            </p>
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              id="customer-csv"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setCsvUploading(true);
                setCsvProgress("読み込み中...");
                const text = await file.text();
                const lines = text.split(/\r?\n/).filter((l) => l.trim());
                let count = 0;
                const total = lines.filter((l) => l.split(",")[0]?.trim()).length;
                for (const line of lines) {
                  const cols = line.split(",").map((c) => c.trim());
                  if (!cols[0]) continue;
                  await createCustomer(clientId, {
                    name: cols[0],
                    code: (cols[1] || "").replace(/^00/, ""),
                    account: cols[2] || "売掛金",
                    account_code: cols[3] || "",
                  });
                  count++;
                  setCsvProgress(`登録中... (${count}/${total})`);
                }
                setCsvUploading(false);
                setCsvProgress("");
                alert(`${count}件の得意先を登録しました`);
                e.target.value = "";
                await loadData();
              }}
            />
            <button
              type="button"
              onClick={() => document.getElementById("customer-csv")?.click()}
              disabled={csvUploading}
              className="px-4 py-2 bg-gray-100 rounded text-sm hover:bg-gray-200 disabled:opacity-50"
            >
              {csvUploading ? csvProgress : "CSVファイルを選択"}
            </button>
          </div>

          {showCustomerForm && (
            <div className="border rounded p-3 mb-4 space-y-2">
              <p className="text-xs font-medium mb-1">個別追加</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">得意先名</label>
                  <input value={customerForm.name} onChange={(e) => setCustomerForm({ ...customerForm, name: e.target.value })} placeholder="株式会社ABC" className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">補助コード</label>
                  <input value={customerForm.code} onChange={(e) => setCustomerForm({ ...customerForm, code: e.target.value })} placeholder="001" className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">勘定科目</label>
                  <input value={customerForm.account} onChange={(e) => setCustomerForm({ ...customerForm, account: e.target.value })} className="w-full p-2 border rounded text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">科目コード</label>
                  <input value={customerForm.account_code} onChange={(e) => setCustomerForm({ ...customerForm, account_code: e.target.value })} className="w-full p-2 border rounded text-sm" />
                </div>
              </div>
              <button
                onClick={async () => {
                  if (!customerForm.name.trim()) return;
                  await createCustomer(clientId, customerForm);
                  setCustomerForm({ name: "", code: "", account: "売掛金", account_code: "" });
                  setShowCustomerForm(false);
                  await loadData();
                }}
                disabled={!customerForm.name.trim()}
                className="px-4 py-2 bg-black text-white rounded text-sm disabled:opacity-50"
              >
                登録
              </button>
            </div>
          )}

          {customers.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">得意先が登録されていません</p>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{customers.length}件登録済み</p>
                <button
                  onClick={async () => {
                    if (!window.confirm(`得意先${customers.length}件を全て削除しますか？`)) return;
                    await deleteAllCustomers(clientId);
                    await loadData();
                  }}
                  className="text-xs px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                >
                  全件削除
                </button>
              </div>
              {customers.map((c: any) => (
                <div key={c.id} className="flex items-start gap-2 text-sm py-2 px-3 rounded bg-gray-50">
                  <div className="flex-1">
                    <p className="font-medium">{c.name}{c.code ? ` (補助: ${c.code})` : ""}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.account || "売掛金"}{c.accountCode ? `(${c.accountCode})` : ""}
                    </p>
                  </div>
                  <button onClick={() => { deleteCustomer(clientId, c.id).then(() => loadData()); }} className="text-muted-foreground hover:text-red-500 shrink-0 px-1">
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default function RulesPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><p className="text-muted-foreground">読み込み中...</p></div>}>
      <RulesPageContent />
    </Suspense>
  );
}
