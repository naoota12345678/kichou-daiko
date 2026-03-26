import { NextRequest, NextResponse } from "next/server";
import { adminAuth } from "@/lib/firebase/admin";

/**
 * Google Cloud Vision API でレシートOCR
 * 高速・高精度。月1,000回まで無料。
 */
export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    await adminAuth.verifyIdToken(token);

    const formData = await req.formData();
    const file = formData.get("file") as File;
    if (!file) {
      return NextResponse.json({ error: "file is required" }, { status: 400 });
    }

    const fileBuffer = Buffer.from(await file.arrayBuffer());
    const base64Image = fileBuffer.toString("base64");

    // Google Cloud Vision API呼び出し（APIキー方式）
    const apiKey = process.env.GOOGLE_VISION_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: "Vision API key not configured" }, { status: 500 });
    }
    const visionRes = await fetch(
      `https://vision.googleapis.com/v1/images:annotate?key=${apiKey}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          requests: [
            {
              image: { content: base64Image },
              features: [{ type: "TEXT_DETECTION" }],
            },
          ],
        }),
      }
    );

    if (!visionRes.ok) {
      const err = await visionRes.text();
      return NextResponse.json({ error: `Vision API error: ${err}` }, { status: 500 });
    }

    const visionData = await visionRes.json();
    const ocrText =
      visionData.responses?.[0]?.fullTextAnnotation?.text || "";

    if (!ocrText) {
      return NextResponse.json({
        amount: 0,
        invoiceNumber: "",
        date: "",
        vendor: "",
        ocrText: "(テキストを検出できませんでした)",
      });
    }

    const result = extractReceiptData(ocrText);
    return NextResponse.json(result);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

function extractReceiptData(text: string) {
  const lines = text.split("\n");

  // 合計金額の抽出（「合計」の近くの金額を優先）
  let amount = 0;

  // まず「合計」行を探す
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/合計|お買上|お買い上げ|総額|税込合計/.test(line)) {
      // 同じ行から金額を取得
      const sameLine = line.match(/[¥￥]?\s*([\d,]+)\s*円?/);
      if (sameLine) {
        const val = parseInt(sameLine[1].replace(/,/g, ""));
        if (val > amount) amount = val;
        continue;
      }
      // 次の行から金額を取得
      if (i + 1 < lines.length) {
        const nextLine = lines[i + 1].match(/[¥￥]?\s*([\d,]+)\s*円?/);
        if (nextLine) {
          const val = parseInt(nextLine[1].replace(/,/g, ""));
          if (val > amount) amount = val;
        }
      }
    }
  }

  // 合計が見つからなければ最大の金額を採用
  if (amount === 0) {
    for (const line of lines) {
      const matches = line.matchAll(/[¥￥]?\s*([\d,]+)\s*円/g);
      for (const m of matches) {
        const val = parseInt(m[1].replace(/,/g, ""));
        if (val > amount && val < 10000000) amount = val;
      }
    }
  }

  // T番号（インボイス番号）
  let invoiceNumber = "";
  const tMatch = text.match(/T\s*\d{13}/);
  if (tMatch) {
    invoiceNumber = tMatch[0].replace(/\s/g, "");
  }

  // 日付
  let date = "";
  const datePatterns = [
    /(\d{4})[\/\-年\.](\d{1,2})[\/\-月\.](\d{1,2})/,
    /令和\s*(\d{1,2})[\/\-年\.](\d{1,2})[\/\-月\.](\d{1,2})/,
  ];
  for (const pattern of datePatterns) {
    const m = text.match(pattern);
    if (m) {
      let y = parseInt(m[1]);
      if (y < 100) y += (pattern.source.includes("令和") ? 2018 : 2000);
      const mo = String(parseInt(m[2])).padStart(2, "0");
      const d = String(parseInt(m[3])).padStart(2, "0");
      date = `${y}-${mo}-${d}`;
      break;
    }
  }

  // 店名（最初の数行から、それっぽいものを取得）
  let vendor = "";
  for (const line of lines.slice(0, 8)) {
    const l = line.trim();
    if (
      l.length >= 2 &&
      l.length <= 30 &&
      !l.match(/^\d/) &&
      !l.match(/^[¥￥]/) &&
      !l.match(/^(電話|TEL|tel|〒|住所|レシート|領収書|No\.|#|\d{4}[\/\-])/) &&
      !l.match(/^(店舗|担当|レジ)/)
    ) {
      vendor = l;
      break;
    }
  }

  return {
    amount,
    invoiceNumber,
    date,
    vendor,
  };
}
