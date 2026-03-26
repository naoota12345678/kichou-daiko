"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import type { CsvFormat, JournalEntry } from "@/lib/models";

const FORMAT_OPTIONS: { value: CsvFormat; label: string }[] = [
  { value: "generic", label: "汎用CSV" },
  { value: "freee", label: "freee" },
  { value: "yayoi", label: "弥生会計" },
  { value: "mf", label: "MFクラウド" },
  { value: "zaimu_r4", label: "財務応援R4" },
];

export function CsvExportForm() {
  const { user } = useAuth();
  const [format, setFormat] = useState<CsvFormat>("generic");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [preview, setPreview] = useState("");
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    if (!user) return;
    setLoading(true);
    try {
      const idToken = await user.getIdToken();
      const res = await fetch("/api/csv/generate", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${idToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ format, startDate, endDate }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPreview(data.csv);
      setEntries(data.entries || []);
      toast.success(`${data.count}件の仕訳を生成しました`);
    } catch (e: any) {
      toast.error(`CSV生成に失敗: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!preview) return;
    const encoding = format === "zaimu_r4" ? "shift_jis" : "utf-8";
    const bom = encoding === "utf-8" ? "\uFEFF" : "";
    const blob = new Blob([bom + preview], {
      type: `text/csv;charset=${encoding}`,
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `仕訳_${format}_${startDate || "all"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>仕訳CSV生成</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>出力形式</Label>
            <Select value={format} onValueChange={(v) => setFormat(v as CsvFormat)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FORMAT_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>開始日</Label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>終了日</Label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>

          <Button onClick={handleGenerate} disabled={loading}>
            {loading ? "生成中..." : "仕訳を生成"}
          </Button>
        </CardContent>
      </Card>

      {preview && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>プレビュー ({entries.length}件)</span>
              <Button size="sm" onClick={handleDownload}>
                ダウンロード
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Textarea
              readOnly
              value={preview}
              rows={15}
              className="font-mono text-xs"
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
