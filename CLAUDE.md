# 記帳代行ツール 開発ルール

## ⚠️ 絶対に守ること

- **Vercel `web` プロジェクト（dentyo.romu.ai / dentyo-80203）には絶対に触らない**
- デプロイ先・変更先は必ずユーザーに確認してから作業する
- 本番環境の環境変数を確認なく変更しない

## プロジェクト構成

- `api/` - FastAPI (Cloud Run) - レシートOCR + 仕訳API
- `web/` - Next.js (Vercel) - フロントエンド
- `scraper-api/` - 旧コード（参考用、デプロイ対象外）

## 接続先一覧

| 項目 | 値 |
|---|---|
| Firebase | kityou-ea085（オーナー: info@hasebe-sr-office.com） |
| Vercel プロジェクト | kichou-daiko（https://kichou-daiko.vercel.app） |
| Cloud Run API | https://kichou-api-845579272926.asia-northeast1.run.app |
| GCPプロジェクト | kityou-ea085 |
| gcloudアカウント（GCP操作用） | info@hasebe-sr-office.com |
| Google Drive レシート保存先 | フォルダID: 1BdIyAHvqil2VTE9UWysVuFKAKyYLu0Cy |

### 触ってはいけないプロジェクト

| 項目 | 値 |
|---|---|
| Vercel `web` | dentyo.romu.ai（Firebase: dentyo-80203）→ 別アプリ、触るな |

## デプロイコマンド（必ずこの通りに実行）

### Cloud Run (api)
```bash
cd /c/Users/naoot/Desktop/claude/acc-hasebe/api && gcloud config set account info@hasebe-sr-office.com && gcloud run deploy kichou-api --source . --region asia-northeast1 --project kityou-ea085 --allow-unauthenticated
```

### Vercel (web) - kichou-daikoプロジェクトにデプロイ
```bash
cd /c/Users/naoot/Desktop/claude/acc-hasebe/web && npx vercel --prod --yes
```
※ デプロイ前に `web/.vercel/project.json` が `kichou-daiko` を指していることを確認すること

## 開発ルール

- 変更は必要最小限にする。動いているものを壊さない
- 聞かれたことだけ直す。「ついでに改善」はしない
- 一度に複数の問題を直す場合も、各修正は独立させる
- 修正前に影響範囲を考える
- デプロイ前にリンク先プロジェクトを必ず確認する

## アーキテクチャ

### 処理フロー
```
レシート撮影/アップロード
  → Google Vision OCR（テキスト抽出）
  → Haiku 一次判定（仕訳パターンマスタ参照）
    ├─ confidence: high → 確定
    └─ confidence: low  → Opus 二次判定（根拠付き）
  → Google Driveに画像保存（顧問先/月/現金orカード）
  → 結果表示 → 確認/修正 → CSV出力（財務応援R4形式）
```

### Firestore構造（kityou-ea085）
```
users/{uid}           - officeId, email
offices/{officeId}/
  clients/{clientId}/
    patterns/         - 仕訳パターンマスタ
    receipts/         - レシート + 仕訳結果 + DriveファイルID
```

### Google Drive保存構造
```
レシートアプリ/
  └── 顧問先名/
      └── YYYY-MM/
          ├── 現金/
          │   └── 日付_店名_¥金額.jpg
          └── カード/
              └── 日付_店名_¥金額.jpg
```

### CSV出力
- 財務応援R4形式（現金/カード別）
- 汎用CSV（判断根拠付き）
