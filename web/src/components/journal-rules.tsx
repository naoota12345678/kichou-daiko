"use client";

import { useState, useEffect } from "react";
import { listRules, createRule, deleteRule } from "@/lib/api";

interface Rule {
  id: string;
  text: string;
}

interface Props {
  clientId: string;
}

export function JournalRules({ clientId }: Props) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [newRule, setNewRule] = useState("");
  const [loading, setLoading] = useState(false);

  const loadRules = async () => {
    if (!clientId) return;
    try {
      const data = await listRules(clientId);
      setRules(data.rules || []);
    } catch (e) {
      console.error("Failed to load rules:", e);
    }
  };

  useEffect(() => {
    loadRules();
  }, [clientId]);

  const handleAdd = async () => {
    if (!newRule.trim()) return;
    setLoading(true);
    try {
      await createRule(clientId, newRule.trim());
      setNewRule("");
      await loadRules();
    } catch (e) {
      console.error("Failed to add rule:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (ruleId: string) => {
    try {
      await deleteRule(clientId, ruleId);
      await loadRules();
    } catch (e) {
      console.error("Failed to delete rule:", e);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-4">
      <h3 className="font-medium text-sm mb-2">仕訳ルール</h3>
      <p className="text-xs text-[var(--muted-foreground)] mb-3">
        この顧問先の仕訳ルールを追加できます。レシート処理時にAIが参照します。
      </p>

      <div className="flex gap-2 mb-3">
        <input
          placeholder="例: ドラッグストアでの購入は全て消耗品費760"
          value={newRule}
          onChange={(e) => setNewRule(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 p-2 border border-[var(--border)] rounded text-sm"
        />
        <button
          onClick={handleAdd}
          disabled={loading || !newRule.trim()}
          className="px-4 py-2 bg-[var(--primary)] text-white rounded text-sm disabled:opacity-50"
        >
          追加
        </button>
      </div>

      {rules.length === 0 ? (
        <p className="text-xs text-[var(--muted-foreground)] py-2">
          ルールが登録されていません
        </p>
      ) : (
        <ul className="space-y-1">
          {rules.map((rule, i) => (
            <li
              key={rule.id}
              className="flex items-start gap-2 text-sm py-2 px-3 rounded bg-[var(--muted)]"
            >
              <span className="text-[var(--muted-foreground)] shrink-0">{i + 1}.</span>
              <span className="flex-1">{rule.text}</span>
              <button
                onClick={() => handleDelete(rule.id)}
                className="text-[var(--muted-foreground)] hover:text-red-500 shrink-0 px-1"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
