"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { href: "/scrape", label: "EC取得" },
  { href: "/receipts/upload", label: "レシート" },
  { href: "/csv", label: "CSV出力" },
  { href: "/settings", label: "設定" },
];

export function Header() {
  const { user, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="border-b bg-white">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/dashboard" className="flex items-center">
          <img src="/logo-nav.png" alt="dentyo" className="h-10" />
        </Link>

        {/* PC: 横並びナビ */}
        <nav className="hidden md:flex items-center gap-4 text-sm">
          {NAV_ITEMS.map((item) => (
            <Link key={item.href} href={item.href} className="hover:underline">
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

        {/* モバイル: ハンバーガーメニュー */}
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

      {/* モバイルメニュー展開 */}
      {menuOpen && (
        <div className="md:hidden border-t bg-white px-4 py-3 space-y-3">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
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
