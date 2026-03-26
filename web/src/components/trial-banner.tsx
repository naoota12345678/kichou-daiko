"use client";

import { usePlan } from "@/hooks/use-plan";

export function TrialBanner() {
  const { loading, plan, trialExpired, daysLeft } = usePlan();

  if (loading || plan === "basic") return null;

  if (trialExpired) {
    return (
      <div className="bg-red-50 border-b border-red-200 px-4 py-3 text-center">
        <p className="text-sm font-medium text-red-800">
          無料トライアル期間が終了しました
        </p>
        <p className="text-xs text-red-600 mt-1">
          引き続きご利用いただくには、お申し込みが必要です。
          <a href="mailto:contact@romu.ai" className="underline ml-1">contact@romu.ai</a> までご連絡ください。
        </p>
      </div>
    );
  }

  if (daysLeft <= 3) {
    return (
      <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-2 text-center">
        <p className="text-xs text-yellow-800">
          無料トライアル残り <strong>{daysLeft}日</strong> です。
          継続をご希望の方は <a href="mailto:contact@romu.ai" className="underline">contact@romu.ai</a> へ。
        </p>
      </div>
    );
  }

  return null;
}
