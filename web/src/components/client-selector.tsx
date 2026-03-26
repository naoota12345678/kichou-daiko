"use client";

import { useState, useEffect } from "react";
import { listClients, createClient } from "@/lib/api";

interface Props {
  selectedId: string;
  onSelect: (id: string, name: string) => void;
}

interface Client {
  id: string;
  name: string;
  code?: string;
}

export function ClientSelector({ selectedId, onSelect }: Props) {
  const [clients, setClients] = useState<Client[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");

  const loadClients = async () => {
    try {
      const data = await listClients();
      const sorted = (data.clients || []).sort((a: Client, b: Client) =>
        a.name.localeCompare(b.name, "ja")
      );
      setClients(sorted);
    } catch (e) {
      console.error("Failed to load clients:", e);
    }
  };

  useEffect(() => {
    loadClients();
  }, []);

  const handleAdd = async () => {
    if (!newName.trim()) return;
    try {
      await createClient(newName.trim(), newCode.trim());
      setNewName("");
      setNewCode("");
      setShowAdd(false);
      await loadClients();
    } catch (e) {
      console.error("Failed to create client:", e);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    if (!id) return;
    const client = clients.find((c) => c.id === id);
    if (client) onSelect(client.id, client.name);
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-4">
      <div className="flex items-center gap-3 flex-wrap">
        <label className="font-medium text-sm">顧問先:</label>
        <select
          value={selectedId}
          onChange={handleChange}
          className="p-3 border border-[var(--border)] rounded text-base min-w-[200px]"
        >
          <option value="">選択してください</option>
          {clients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}{c.code ? ` (${c.code})` : ""}
            </option>
          ))}
        </select>
        <button
          onClick={() => setShowAdd(true)}
          className="px-3 py-3 rounded text-sm bg-[var(--muted)] hover:bg-[var(--border)]"
        >
          + 追加
        </button>
      </div>

      {showAdd && (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <input
            placeholder="顧問先名"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="p-2 border border-[var(--border)] rounded text-sm"
          />
          <input
            placeholder="コード（任意）"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
            className="p-2 border border-[var(--border)] rounded text-sm w-28"
          />
          <button
            onClick={handleAdd}
            className="px-3 py-2 bg-[var(--primary)] text-white rounded text-sm"
          >
            登録
          </button>
          <button
            onClick={() => setShowAdd(false)}
            className="px-3 py-2 text-sm text-[var(--muted-foreground)]"
          >
            キャンセル
          </button>
        </div>
      )}
    </div>
  );
}
