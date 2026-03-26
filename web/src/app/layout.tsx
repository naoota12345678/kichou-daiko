import type { Metadata } from "next";
import { Noto_Sans_JP } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const notoSansJP = Noto_Sans_JP({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "電帳ツール - 電子帳簿保存法対応 経理自動化",
  description: "領収書のアップロード・整理・仕訳CSV出力を自動化",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#ffffff" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="dentyo" />
        <link rel="apple-touch-icon" href="/logo.png" />
      </head>
      <body className={`${notoSansJP.variable} font-sans antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
