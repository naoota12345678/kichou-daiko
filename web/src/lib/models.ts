/** データモデル (Python models.py の TypeScript移植) */

export type Source = "Amazon" | "楽天" | "レシート" | "Yahoo";

export interface OrderItem {
  orderDate: string; // YYYY-MM-DD
  vendor: string;
  productName: string;
  amount: number; // 税込金額 (integer円)
  invoiceNumber?: string; // インボイス番号 T+13桁
  source: Source;
  orderId?: string;
  paymentMethod?: string;
}

export interface JournalEntry {
  entryDate: string; // YYYY-MM-DD
  debitAccount: string; // 借方科目
  debitAmount: number;
  creditAccount: string; // 貸方科目
  creditAmount: number;
  description: string; // 摘要
  confidence: "auto" | "unknown";
}

export interface UserSettings {
  accountingSoftware: string; // generic / freee / yayoi / mf / zaimu_r4
  fiscalYearStartMonth: number; // 1-12
  companyName: string;
  driveRootFolderId: string;
  driveConnected: boolean;
  plan?: "trial" | "basic"; // trial=無料期間, basic=課金済み
  createdAt?: string; // ISO8601 初回登録日時
}

export type CsvFormat = "generic" | "freee" | "yayoi" | "mf" | "zaimu_r4";
