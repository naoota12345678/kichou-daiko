"use client";

import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { getClientDb } from "@/lib/firebase/client";
import { useAuth } from "@/lib/auth-context";
import type { UserSettings } from "@/lib/models";

const DEFAULT_SETTINGS: UserSettings = {
  accountingSoftware: "generic",
  fiscalYearStartMonth: 1,
  companyName: "",
  driveRootFolderId: "",
  driveConnected: false,
};

export function useUserSettings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      setSettings(DEFAULT_SETTINGS);
      setLoading(false);
      return;
    }

    const unsub = onSnapshot(doc(getClientDb(), "users", user.uid), (snap) => {
      if (snap.exists()) {
        setSettings({ ...DEFAULT_SETTINGS, ...snap.data() } as UserSettings);
      }
      setLoading(false);
    });

    return unsub;
  }, [user]);

  return { settings, loading };
}
