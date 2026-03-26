"use client";

import { useUserSettings } from "./use-user-settings";

const TRIAL_DAYS = 7;

export function usePlan() {
  const { settings, loading } = useUserSettings();

  if (loading) return { loading: true, active: true, trialExpired: false, plan: undefined, daysLeft: 0 };

  const plan = settings.plan || "trial";

  // 課金済みなら常にアクティブ
  if (plan === "basic") {
    return { loading: false, active: true, trialExpired: false, plan: "basic" as const, daysLeft: 0 };
  }

  // トライアル期間チェック
  const createdAt = settings.createdAt ? new Date(settings.createdAt) : null;
  if (!createdAt) {
    // createdAtがない古いユーザー → アクティブとして扱う
    return { loading: false, active: true, trialExpired: false, plan: "trial" as const, daysLeft: TRIAL_DAYS };
  }

  const now = new Date();
  const diffMs = now.getTime() - createdAt.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  const daysLeft = Math.max(0, Math.ceil(TRIAL_DAYS - diffDays));
  const trialExpired = diffDays > TRIAL_DAYS;

  return {
    loading: false,
    active: !trialExpired,
    trialExpired,
    plan: "trial" as const,
    daysLeft,
  };
}
