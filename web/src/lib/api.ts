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

// クライアント
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

// 仕訳ルール
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

// レシート処理
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

// レシート一覧
export async function listReceipts(clientId: string) {
  const res = await apiFetch(`/api/clients/${clientId}/receipts`);
  return res.json();
}
