"use client";

import { useCallback, useState } from "react";
import { useAuth } from "@/lib/auth-context";

export function useDrive() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);

  const getAuthHeaders = useCallback(async () => {
    if (!user) throw new Error("Not authenticated");
    const idToken = await user.getIdToken();
    return { Authorization: `Bearer ${idToken}` };
  }, [user]);

  const uploadReceipt = useCallback(
    async (formData: FormData) => {
      setLoading(true);
      try {
        const headers = await getAuthHeaders();
        const res = await fetch("/api/drive/upload", {
          method: "POST",
          headers,
          body: formData,
        });
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
      } finally {
        setLoading(false);
      }
    },
    [getAuthHeaders]
  );

  const listFiles = useCallback(async () => {
    const headers = await getAuthHeaders();
    const res = await fetch("/api/drive/list", { headers });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()).files as string[];
  }, [getAuthHeaders]);

  const setupFolders = useCallback(
    async (fiscalYearStartMonth: number) => {
      setLoading(true);
      try {
        const headers = await getAuthHeaders();
        const res = await fetch("/api/drive/setup-folders", {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({ fiscalYearStartMonth }),
        });
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
      } finally {
        setLoading(false);
      }
    },
    [getAuthHeaders]
  );

  return { uploadReceipt, listFiles, setupFolders, loading };
}
