# dentyo 管理者マニュアル

## 顧客管理の流れ

### 1. 新規顧客がサインアップしたとき

何もしなくてOK。自動で以下が設定されます：
- `plan: "trial"`
- `createdAt: (登録日時)`
- 7日間は全機能が使える

### 2. トライアル期限が近づいたとき（残り3日）

顧客のダッシュボードに黄色いバナーが自動表示されます。
contact@romu.ai への連絡を促すメッセージが出ます。

### 3. トライアル期限が切れたとき（7日経過）

自動で以下がブロックされます：
- ダッシュボードの機能ボタンが非表示（課金案内に差し替わり）
- レシートのアップロードがAPI側で拒否される
- 赤いバナーが表示される

**※ Google Driveに保存済みのデータには影響なし**

### 4. Stripeで入金確認後 → Firestoreを更新

Firebase Console（https://console.firebase.google.com/project/dentyo-80203）で以下を操作：

1. Firestore Database を開く
2. `users` コレクション → 該当ユーザーのドキュメントを選択
3. `plan` フィールドを `"basic"` に変更（なければ追加）
4. 保存

これだけで課金済みユーザーとして全機能が使えるようになります。

### 5. 既存の3名の顧客を課金済みにする

Firebase Console で各ユーザーのドキュメントに以下を設定：

```
plan: "basic"
```

`createdAt` がないユーザーはトライアル制限がかからない仕様なので、
既存ユーザーは急がなくても大丈夫ですが、早めに設定しておくと安心です。

---

## Firestoreユーザードキュメントの構造

パス: `users/{uid}`

| フィールド | 値 | 説明 |
|---|---|---|
| `plan` | `"trial"` or `"basic"` | トライアル or 課金済み |
| `createdAt` | ISO8601文字列 | 初回登録日時 |
| `companyName` | 文字列 | 会社名 |
| `accountingSoftware` | `"generic"` / `"freee"` / `"yayoi"` / `"mf"` / `"zaimu_r4"` | 会計ソフト |
| `driveConnected` | boolean | Drive接続済みか |
| `driveRootFolderId` | 文字列 | DriveのaccフォルダID |

---

## 顧客への解約対応

顧客から解約の連絡があった場合：

1. Stripeで定期課金を停止
2. Firebase Console で `plan` を `"trial"` に戻す（任意）
3. Google Driveのデータは顧客のものなので何もしない

**「データはそのまま残ります」と伝えてOK。**

---

## トラブルシューティング

### 課金済みなのにブロックされる
→ Firestoreの `plan` が `"basic"` になっているか確認

### トライアルが切れていないのにブロックされる
→ `createdAt` の日時が正しいか確認（7日以上前になっていないか）

### 顧客のuidがわからない
→ Firebase Console → Authentication → ユーザー一覧からメールアドレスで検索
