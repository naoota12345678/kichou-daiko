"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { collection, onSnapshot, query, orderBy, limit } from "firebase/firestore";
import { getClientDb } from "@/lib/firebase/client";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/header";
import { RemoteBrowser } from "@/components/remote-browser";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";

const SITES = [
  { value: "amazon", label: "Amazon" },
  { value: "rakuten", label: "楽天市場" },
  { value: "yahoo", label: "Yahoo ショッピング" },
];

const SCRAPER_API_URL = process.env.NEXT_PUBLIC_SCRAPER_API_URL || "";

interface ScrapedItem {
  orderDate: string;
  vendor: string;
  productName: string;
  amount: number;
  source: string;
  orderId?: string;
}

export default function ScrapePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [site, setSite] = useState("amazon");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [wsUrl, setWsUrl] = useState("");
  const [browserActive, setBrowserActive] = useState(false);
  const [items, setItems] = useState<ScrapedItem[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [jobId, setJobId] = useState("");
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // Firestoreでジョブ結果を監視（WebSocket切断後も結果を取得）
  useEffect(() => {
    if (!user || !polling) return;

    const db = getClientDb();
    const jobsRef = collection(db, "users", user.uid, "jobs");
    const q = query(jobsRef, orderBy("createdAt", "desc"), limit(1));

    const unsub = onSnapshot(q, (snapshot) => {
      snapshot.forEach((doc) => {
        const data = doc.data();
        if (data.status === "complete" && data.items?.length > 0) {
          setItems(data.items);
          setUploadedFiles(data.uploadedFiles || []);
          setBrowserActive(false);
          setWsUrl("");
          setPolling(false);
          toast.success(`${data.items.length}件の注文を取得しました`);
        } else if (data.status === "error") {
          setErrors([data.error || "スクレイピングエラー"]);
          setPolling(false);
        }
      });
    });

    return unsub;
  }, [user, polling]);

  const handleStart = async () => {
    if (!user || !SCRAPER_API_URL) {
      toast.error("スクレイピングAPIが設定されていません");
      return;
    }

    setItems([]);
    setUploadedFiles([]);
    setErrors([]);

    try {
      const idToken = await user.getIdToken();
      const apiHost = SCRAPER_API_URL.replace("https://", "").replace("http://", "");
      const wsScheme = SCRAPER_API_URL.startsWith("https") ? "wss" : "ws";
      const url = `${wsScheme}://${apiHost}/api/browser/ws?token=${idToken}&site=${site}&year=${year}`;
      setWsUrl(url);
      setBrowserActive(true);
    } catch (e: any) {
      toast.error(`起動失敗: ${e.message}`);
    }
  };

  const handleComplete = useCallback(
    (newItems: ScrapedItem[], files: string[]) => {
      if (newItems.length > 0) {
        setItems(newItems);
        setUploadedFiles(files);
        setBrowserActive(false);
        setWsUrl("");
        setPolling(false);
        toast.success(`${newItems.length}件の注文を取得しました`);
      }
      // 0件の場合はFirestore監視で結果を待つ（スクレイピング中通知）
      if (newItems.length === 0) {
        setPolling(true);
      }
    },
    []
  );

  const handleError = useCallback((message: string) => {
    // スクレイピング中のWebSocket切断はエラーではない（Firestore監視で結果取得）
    if (polling) return;
    setErrors((prev) => [...prev, message]);
    toast.error(message);
  }, [polling]);

  const handleStop = () => {
    setBrowserActive(false);
    setWsUrl("");
  };

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => String(currentYear - i));

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">EC注文取得</h1>

        {!browserActive && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>注文データを取得</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!SCRAPER_API_URL && (
                <div className="rounded-md bg-yellow-50 p-3 text-sm text-yellow-800">
                  スクレイピングAPIのURLが設定されていません。
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>ECサイト</Label>
                  <Select value={site} onValueChange={(v) => v && setSite(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SITES.map((s) => (
                        <SelectItem key={s.value} value={s.value}>
                          {s.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>年度</Label>
                  <Select value={year} onValueChange={(v) => v && setYear(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {years.map((y) => (
                        <SelectItem key={y} value={y}>
                          {y}年
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button
                onClick={handleStart}
                disabled={!SCRAPER_API_URL}
                className="w-full"
              >
                ログインして注文データを取得
              </Button>

              <div className="rounded-md bg-gray-50 p-3 text-xs text-muted-foreground">
                <p className="font-medium text-gray-700 mb-1">あなたのパスワードは保存しません</p>
                <p>
                  ログイン情報はリモートブラウザ上でのみ使用され、当社サーバーには一切記録されません。セッション終了後にすべて破棄されます。
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {browserActive && wsUrl && (
          <div className="mb-6 space-y-4">
            <RemoteBrowser
              wsUrl={wsUrl}
              onComplete={handleComplete}
              onError={handleError}
            />
            <Button variant="outline" onClick={handleStop} className="w-full">
              キャンセル
            </Button>
          </div>
        )}

        {polling && !browserActive && (
          <Card className="mb-6">
            <CardContent className="py-8 text-center">
              <p className="text-lg font-medium">注文データ取得中...</p>
              <p className="mt-2 text-sm text-muted-foreground">
                サーバーで処理中です。このページを離れても大丈夫です。
              </p>
            </CardContent>
          </Card>
        )}

        {errors.length > 0 && (
          <Card className="mb-6 border-red-200">
            <CardHeader>
              <CardTitle className="text-red-600">エラー</CardTitle>
            </CardHeader>
            <CardContent>
              {errors.map((e, i) => (
                <p key={i} className="text-sm text-red-600">{e}</p>
              ))}
            </CardContent>
          </Card>
        )}

        {uploadedFiles.length > 0 && (
          <Card className="mb-6 border-green-200">
            <CardContent className="py-4">
              <p className="text-green-700 font-medium">
                Google Drive の「acc」フォルダに保存しました（{uploadedFiles.length}件）
              </p>
              <ul className="mt-2 space-y-1">
                {uploadedFiles.map((f, i) => (
                  <li key={i} className="font-mono text-xs text-muted-foreground truncate">{f}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {items.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>取得結果 ({items.length}件)</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>日付</TableHead>
                    <TableHead>取引先</TableHead>
                    <TableHead>品名</TableHead>
                    <TableHead className="text-right">金額</TableHead>
                    <TableHead>元</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item, i) => (
                    <TableRow key={i}>
                      <TableCell>{item.orderDate}</TableCell>
                      <TableCell>{item.vendor}</TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {item.productName}
                      </TableCell>
                      <TableCell className="text-right">
                        ¥{item.amount.toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{item.source}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
