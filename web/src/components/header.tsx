"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";

export function Header() {
  const { user, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientName, setClientName] = useState("");
  const pathname = usePathname();

  // localStorageから選択中の顧問先を取得
  useEffect(() => {
    try {
      const saved = localStorage.getItem("selectedClient");
      if (saved) {
        const { id, name } = JSON.parse(saved);
        if (id) { setClientId(id); setClientName(name); }
      }
    } catch {}
  }, [pathname]);

  const buildHref = (base: string) => {
    if (!clientId) return base;
    return `${base}?clientId=${clientId}&clientName=${encodeURIComponent(clientName)}`;
  };

  const NAV_ITEMS = [
    { href: buildHref("/receipts"), label: "レシート" },
    { href: buildHref("/handwritten"), label: "手書き領収書" },
    { href: buildHref("/journals"), label: "仕訳一覧" },
    { href: buildHref("/rules"), label: "仕訳ルール" },
    { href: buildHref("/csv"), label: "CSV出力" },
  ];

  return (
    <header className="border-b bg-white">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/dashboard" className="font-bold text-lg">
          記帳代行ツール
        </Link>

        <nav className="hidden md:flex items-center gap-4 text-sm">
          {NAV_ITEMS.map((item) => (
            <Link key={item.label} href={item.href} className="hover:underline">
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {user && (
            <>
              <span className="text-sm text-muted-foreground">
                {user.displayName || user.email}
              </span>
              <Button variant="outline" size="sm" onClick={signOut}>
                ログアウト
              </Button>
            </>
          )}
        </div>

        <button
          className="md:hidden p-2"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="メニュー"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {menuOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {menuOpen && (
        <div className="md:hidden border-t bg-white px-4 py-3 space-y-3">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className="block py-2 text-sm hover:underline"
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </Link>
          ))}
          {user && (
            <div className="pt-2 border-t flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {user.displayName || user.email}
              </span>
              <Button variant="outline" size="sm" onClick={signOut}>
                ログアウト
              </Button>
            </div>
          )}
        </div>
      )}
    </header>
  );
}
