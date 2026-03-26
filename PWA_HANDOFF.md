# PWA版 開発引き継ぎメモ

## 概要

CLI版（`src/acc_tool/`）で作った経理半自動化ツールをPWA（Next.js + Vercel）に移行する。
設計書: `accounting_platform_final_v3.md`
電帳法要件: `電帳法対応メモ.md`

## 既に完成しているもの（CLI版）

### スクレイパー（ローカル実行のまま）
- `scrapers/amazon_scraper.py` — Amazon注文履歴の全ページ自動取得
- `scrapers/rakuten_scraper.py` — 楽天注文履歴（__INITIAL_STATE__ JSONから取得）
- `scrapers/yahoo_scraper.py` — Yahoo Shopping（bodyテキストパース）
- 各サイトの領収書PDFダウンロード機能
- Playwrightベース、セッション永続化（`~/.acc-tool/`に保存）

### ロジック（PWAに移植するもの）
- `drive/namer.py` — 電帳法ファイル名生成（`YYYYMMDD_取引先_品名_金額.pdf`）
- `drive/namer.py:generate_folder_path()` — 年度/月フォルダパス生成（4月始まり対応）
- `drive/dedup.py` — 重複チェック（日付×金額×取引先で判定）
- `csv_gen/rules.py` — 科目推定ルール（キーワードマッチング15カテゴリ）
- `csv_gen/journal.py` — 仕訳CSV生成（generic/freee/弥生/MF/財務応援R4の5形式）
- `compliance/regulation.py` — 事務処理規程テンプレート生成
- `models.py` — データモデル（OrderItem, JournalEntry, Source）

## PWA版の技術構成

```
acc-platform/              # 新規Next.jsプロジェクト
├── app/                   # App Router
│   ├── page.tsx           # ホーム画面
│   ├── login/             # Firebase Auth ログイン
│   ├── capture/           # レシート撮影（カメラAPI）
│   ├── receipts/          # 保存済み領収書一覧（検索）
│   ├── import/            # EC取り込み結果の確認
│   ├── settings/          # 初回設定（会計ソフト選択、決算月、ドライブ設定）
│   └── api/
│       ├── ocr/           # Claude Vision OCR
│       ├── drive/         # Google Drive操作
│       ├── csv/           # 仕訳CSV生成
│       └── regulation/    # 事務処理規程生成
├── lib/
│   ├── firebase.ts        # Firebase Auth初期化
│   ├── google-drive.ts    # Drive API操作
│   ├── ocr.ts             # Claude Vision API呼び出し
│   ├── namer.ts           # ファイル名生成（namer.pyの移植）
│   ├── dedup.ts           # 重複チェック（dedup.pyの移植）
│   ├── rules.ts           # 科目推定ルール（rules.pyの移植）
│   └── journal.ts         # 仕訳CSV生成（journal.pyの移植）
├── components/
│   ├── Camera.tsx          # カメラ撮影コンポーネント
│   ├── ReceiptList.tsx     # 領収書一覧
│   └── StatusDashboard.tsx # 月次状況ダッシュボード
├── public/
│   └── manifest.json      # PWA設定
└── next.config.js
```

## 必要なサービス設定

### 1. Google Cloud Platform（新規プロジェクト）
- プロジェクト作成（名前: acc-platform等）
- **Firebase追加**（同じGCPプロジェクト内）
- **Drive API有効化**
- **OAuth 2.0 クライアント作成**（ウェブアプリケーション）
  - リダイレクトURI: `https://your-app.vercel.app/api/auth/callback/google`
  - スコープ: `https://www.googleapis.com/auth/drive.file`（アプリが作ったファイルのみ）

### 2. Firebase
- Authentication有効化
  - Google ログインプロバイダ有効化
- Firestore（ユーザー設定保存用、最小限）
  - `users/{uid}` — 会計ソフト選択、決算月、ドライブフォルダID

### 3. Anthropic
- Claude API キー（レシートOCR用）
- モデル: `claude-haiku-4-5-20251001`（コスト最小）

### 4. Vercel
- Next.jsプロジェクトデプロイ
- 環境変数:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `FIREBASE_API_KEY` / `FIREBASE_AUTH_DOMAIN` etc.
  - `ANTHROPIC_API_KEY`

## 主要な画面フロー

### 初回設定
```
ログイン（Firebase Auth / Google）
→ Googleドライブ連携（OAuth、drive.fileスコープ）
→ 会計ソフト選択（freee/弥生/MF/財務応援R4/汎用）
→ 決算月選択（3月/12月/その他）
→ 事務処理規程自動生成 → ドライブに保存
→ 完了
```

### レシート撮影フロー
```
「レシートを撮る」ボタン
→ カメラ起動（動画 or 写真）
→ 動画の場合: フレーム抽出（ベストフレーム選択）
→ 画像をClaude Vision OCRに送信
→ 店名・金額・日付を取得
→ ファイル名生成: 20260317_セブンイレブン_1080.pdf
→ Googleドライブにアップロード（年度/月/領収書/ フォルダ）
→ 重複チェック（既存ファイルとの照合）
→ 完了表示
```

### EC取り込み（将来的にWebView化、当面はCLI）
```
CLI: acc fetch-amazon --year 2025 -o amazon.csv --receipts ./receipts
→ CSVをPWAにアップロード
→ PWAがドライブに保存 + 仕訳CSV生成
```

## Claude Vision OCR APIの呼び方

```typescript
// api/ocr/route.ts
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic();

export async function POST(req: Request) {
  const { imageBase64, mediaType } = await req.json();

  const response = await anthropic.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 256,
    messages: [{
      role: 'user',
      content: [
        {
          type: 'image',
          source: { type: 'base64', media_type: mediaType, data: imageBase64 },
        },
        {
          type: 'text',
          text: 'このレシート/領収書から以下をJSON形式で抽出してください:\n'
            + '{"date": "YYYY-MM-DD", "vendor": "店名", "amount": 金額(数値), "items": "主な品目"}\n'
            + '読み取れない項目はnullにしてください。',
        },
      ],
    }],
  });

  return Response.json(JSON.parse(response.content[0].text));
}
```

## Google Drive APIの使い方

```typescript
// lib/google-drive.ts

// ファイルアップロード
async function uploadFile(
  accessToken: string,
  file: Blob,
  filename: string,
  folderId: string,
  mimeType: string
): Promise<string> {
  const metadata = {
    name: filename,
    parents: [folderId],
  };

  const form = new FormData();
  form.append('metadata', new Blob([JSON.stringify(metadata)], { type: 'application/json' }));
  form.append('file', file);

  const res = await fetch(
    'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id',
    { method: 'POST', headers: { Authorization: `Bearer ${accessToken}` }, body: form }
  );

  const data = await res.json();
  return data.id;
}

// フォルダ作成（なければ）
async function ensureFolder(
  accessToken: string,
  folderName: string,
  parentId: string
): Promise<string> {
  // 既存検索
  const query = `name='${folderName}' and '${parentId}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false`;
  const res = await fetch(
    `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(query)}&fields=files(id)`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  const data = await res.json();
  if (data.files.length > 0) return data.files[0].id;

  // 作成
  const createRes = await fetch('https://www.googleapis.com/drive/v3/files', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: folderName,
      mimeType: 'application/vnd.google-apps.folder',
      parents: [parentId],
    }),
  });
  const folder = await createRes.json();
  return folder.id;
}
```

## 電帳法ファイル名生成（TypeScript版）

```typescript
// lib/namer.ts
export function generateFilename(
  date: Date,
  vendor: string,
  productName: string,
  amount: number,
  invoiceNumber?: string,
  ext: string = '.pdf'
): string {
  const dateStr = date.toISOString().slice(0, 10).replace(/-/g, '');
  const sanitized = productName.replace(/[\\/:*?"<>|\n\r\t]/g, '').slice(0, 30);
  const parts = [dateStr, vendor, sanitized, String(amount)];
  if (invoiceNumber) parts.push(invoiceNumber);
  return parts.join('_') + ext;
}

export function generateFolderPath(
  fiscalYearStartMonth: number,
  year: number,
  month: number
): string {
  const fiscalYear = month < fiscalYearStartMonth ? year - 1 : year;
  const monthStr = String(month).padStart(2, '0');
  return `${fiscalYear}年度/${monthStr}月/領収書`;
}
```

## ビジネスモデル

- **無料/月500円**: レシート撮影 + OCR + ドライブ保存 + 仕訳CSV（月200枚まで）
- **プロ連携版**: 上記 + Moneytree API連携 + AI判定 + 管理画面（顧問料に含む）
- OCRコスト: 月200枚で約90円 → 500円プランで利益率80%以上

## 注意事項

- Windows環境: print()にUnicode文字（✓⚠→）を使うとcp932エンコードエラー。ASCII-safeに
- Yahoo Shopping: セッション切れやすい + CAPTCHA頻出。初回は手動ログイン+CAPTCHA必須
- 楽天: __INITIAL_STATE__ JSONからデータ取得（DOMセレクタはハッシュ化CSS-in-JS）
- Amazon: ログイン検知はURL依存NG、DOM内容で判定する
- Google Drive: `drive.file`スコープ = アプリが作ったファイルのみアクセス。ユーザーの他ファイルに触れない
