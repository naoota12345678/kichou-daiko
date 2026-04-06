import { getClientAuth } from "@/lib/firebase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

async function getToken(): Promise<string> {
  const auth = getClientAuth();
  const user = auth.currentUser;
  if (!user) throw new Error("ログインしてください");
  return user.getIdToken();
}

async function apiFetch(path: string, options: RequestInit = {}) {
  const token = await getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res;
}

// クライアント（顧問先）
export async function listClients() {
  const res = await apiFetch("/api/clients");
  return res.json();
}

export async function createClient(name: string, code: string = "") {
  const res = await apiFetch("/api/clients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, code }),
  });
  return res.json();
}

// 仕訳パターン
export async function listPatterns(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/patterns`);
  return res.json();
}

export async function createPattern(clientId: string, pattern: {
  keywords: string[];
  vendor_name?: string;
  debit_account: string;
  debit_code?: string;
  credit_account: string;
  credit_code?: string;
  tax_rate?: string;
  tax_category?: string;
  description_template?: string;
}) {
  const res = await apiFetch(`/api/clients/${clientId}/patterns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pattern),
  });
  return res.json();
}

export async function deletePattern(clientId: string, patternId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/patterns/${patternId}`, {
    method: "DELETE",
  });
  return res.json();
}

// 仕訳ルール（テキスト）
export async function listRules(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/rules`);
  return res.json();
}

export async function createRule(clientId: string, text: string) {
  const res = await apiFetch(`/api/clients/${clientId}/rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.json();
}

export async function deleteRule(clientId: string, ruleId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/rules/${ruleId}`, {
    method: "DELETE",
  });
  return res.json();
}

// 追加指示（手書き領収書用）
export async function getInstructions(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/instructions`);
  return res.json();
}

export async function updateInstructions(clientId: string, instructions: string) {
  const res = await apiFetch(`/api/clients/${clientId}/instructions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instructions }),
  });
  return res.json();
}

// 科目コードマスタ
export async function listAccounts(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/accounts`);
  return res.json();
}

export async function createAccount(clientId: string, data: { code: string; name: string }) {
  const res = await apiFetch(`/api/clients/${clientId}/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteAccount(clientId: string, accountId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/accounts/${accountId}`, {
    method: "DELETE",
  });
  return res.json();
}

export async function deleteAllAccounts(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/accounts`, {
    method: "DELETE",
  });
  return res.json();
}

// 得意先マスタ
export async function listCustomers(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/customers`);
  return res.json();
}

export async function createCustomer(clientId: string, data: {
  name: string;
  code?: string;
  account?: string;
  account_code?: string;
}) {
  const res = await apiFetch(`/api/clients/${clientId}/customers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteCustomer(clientId: string, customerId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/customers/${customerId}`, {
    method: "DELETE",
  });
  return res.json();
}

export async function deleteAllCustomers(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/customers`, {
    method: "DELETE",
  });
  return res.json();
}

// レシートアップロードのみ（OCR/仕訳なし）
export async function uploadReceipt(
  file: File,
  clientId: string,
  receiptType: "receipt" | "handwritten" = "receipt",
  instructions: string = "",
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("client_id", clientId);
  formData.append("receipt_type", receiptType);
  if (instructions) formData.append("instructions", instructions);

  const res = await apiFetch("/api/receipts/upload", {
    method: "POST",
    body: formData,
  });
  return res.json();
}

// 未処理レシート一括処理（OCR+仕訳）
export async function processAllUploaded(clientId: string, receiptType?: string) {
  const params = receiptType ? `?receipt_type=${receiptType}` : "";
  const res = await apiFetch(`/api/clients/${clientId}/process-all${params}`, {
    method: "POST",
  });
  return res.json();
}

// レシート処理（アップロード+OCR+仕訳を同時に）
export async function processReceipt(file: File, clientId: string) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("client_id", clientId);

  const res = await apiFetch("/api/receipts/process", {
    method: "POST",
    body: formData,
  });
  return res.json();
}

// レシート・仕訳一覧
export async function listReceipts(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/receipts`);
  return res.json();
}

// 仕訳修正
export async function updateJournal(clientId: string, receiptId: string, data: {
  debit_account?: string;
  debit_code?: string;
  credit_account?: string;
  credit_code?: string;
  tax_rate?: string;
  description?: string;
  vendor?: string;
  amount?: number;
}) {
  const res = await apiFetch(`/api/clients/${clientId}/receipts/${receiptId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

// レシート削除
export async function deleteReceipt(clientId: string, receiptId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/receipts/${receiptId}`, {
    method: "DELETE",
  });
  return res.json();
}

// エラーレシート一括削除
export async function deleteErrorReceipts(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/receipts/errors`, {
    method: "DELETE",
  });
  return res.json();
}

// 仕訳確定
export async function confirmJournal(clientId: string, receiptId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/receipts/${receiptId}/confirm`, {
    method: "POST",
  });
  return res.json();
}

// CSV出力
export async function exportCsv(
  clientId: string,
  format: "zaimu_ouen" | "generic" = "zaimu_ouen",
  status: "confirmed" | "all" = "confirmed",
  paymentMethod: "" | "現金" | "カード" = "",
  dateFrom: string = "",
  dateTo: string = "",
): Promise<{ blob: Blob; text: string }> {
  const params = new URLSearchParams({ format, status, payment_method: paymentMethod });
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const res = await apiFetch(`/api/clients/${clientId}/export?${params}`);
  const blob = await res.blob();
  // プレビュー用テキスト：財務応援はShift-JIS、汎用はUTF-8
  let text: string;
  if (format === "zaimu_ouen") {
    const buf = await blob.arrayBuffer();
    const decoder = new TextDecoder("shift_jis");
    text = decoder.decode(buf);
  } else {
    text = await blob.text();
  }
  return { blob, text };
}
