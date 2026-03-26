"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";

interface DriveFile {
  name: string;
  date?: string;
  vendor?: string;
  amount?: string;
}

function parseReceiptFilename(name: string): DriveFile {
  const stem = name.replace(/\.[^.]+$/, "");
  const parts = stem.split("_");
  if (parts.length >= 4 && /^\d{8}$/.test(parts[0])) {
    const d = parts[0];
    return {
      name,
      date: `${d.slice(0, 4)}/${d.slice(4, 6)}/${d.slice(6, 8)}`,
      vendor: parts[1],
      amount: parts.find((p, i) => i >= 2 && /^\d+$/.test(p) && !/^T\d{13}$/.test(p)) || "",
    };
  }
  return { name };
}

export function ReceiptList() {
  const { user } = useAuth();
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterDate, setFilterDate] = useState("");
  const [filterVendor, setFilterVendor] = useState("");

  useEffect(() => {
    if (!user) return;
    loadFiles();
  }, [user]);

  const loadFiles = async () => {
    try {
      const idToken = await user!.getIdToken();
      const res = await fetch("/api/drive/list", {
        headers: { Authorization: `Bearer ${idToken}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setFiles(
        (data.files as string[]).map(parseReceiptFilename)
      );
    } catch (e: any) {
      toast.error(`ファイル一覧の取得に失敗: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const filtered = files.filter((f) => {
    if (filterDate && f.date && !f.date.includes(filterDate)) return false;
    if (filterVendor && f.vendor && !f.vendor.includes(filterVendor)) return false;
    return true;
  });

  if (loading) {
    return <p className="text-muted-foreground">読み込み中...</p>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">フィルタ</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-4">
          <div className="space-y-1">
            <Label className="text-xs">日付</Label>
            <Input
              placeholder="2026/03"
              value={filterDate}
              onChange={(e) => setFilterDate(e.target.value)}
              className="w-40"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">取引先</Label>
            <Input
              placeholder="Amazon"
              value={filterVendor}
              onChange={(e) => setFilterVendor(e.target.value)}
              className="w-40"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>日付</TableHead>
                <TableHead>取引先</TableHead>
                <TableHead className="text-right">金額</TableHead>
                <TableHead>ファイル名</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    ファイルがありません
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((f) => (
                  <TableRow key={f.name}>
                    <TableCell>{f.date || "-"}</TableCell>
                    <TableCell>{f.vendor || "-"}</TableCell>
                    <TableCell className="text-right">
                      {f.amount ? `¥${Number(f.amount).toLocaleString()}` : "-"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{f.name}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
