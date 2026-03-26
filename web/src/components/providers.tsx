"use client";

import { useEffect } from "react";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { Toaster } from "@/components/ui/sonner";

function ExtensionBridge() {
  const { user } = useAuth();

  useEffect(() => {
    const handler = async (event: MessageEvent) => {
      if (event.data?.type === "DENTYO_GET_TOKEN" && user) {
        const idToken = await user.getIdToken();
        window.postMessage({ type: "DENTYO_TOKEN_RESPONSE", idToken }, "*");
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [user]);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      {children}
      <ExtensionBridge />
      <Toaster />
    </AuthProvider>
  );
}
