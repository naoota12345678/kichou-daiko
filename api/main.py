"""記帳代行レシート仕訳API"""

from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from datetime import date as date_type, datetime

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials, firestore
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models import ReceiptData, JournalEntry, JournalPattern
from journaling import process_receipt
from csv_export import export_zaimu_ouen, export_generic
from drive_upload import upload_receipt_to_drive, append_to_csv

app = FastAPI(title="記帳代行 仕訳API")

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase
if not firebase_admin._apps:
    if os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"):
        sa = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])
        cred = credentials.Certificate(sa)
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

db = firestore.client()


# ---- Auth ----

def verify_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")
    token = authorization[7:]
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")


def get_office_id(uid: str) -> str:
    """ユーザーが所属する事務所IDを取得"""
    doc = db.collection("users").document(uid).get()
    data = doc.to_dict() or {}
    office_id = data.get("officeId", "")
    if not office_id:
        raise HTTPException(403, "事務所に所属していません")
    return office_id


# ---- Health ----

@app.get("/health")
def health():
    return {"status": "ok"}


# ---- クライアント管理 ----

class ClientCreate(BaseModel):
    name: str
    code: str = ""
    default_tax_rate: str = "10"


@app.get("/api/clients")
def list_clients(authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = db.collection("offices").document(office_id).collection("clients").stream()
    clients = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        clients.append(d)
    return {"clients": clients}


@app.post("/api/clients")
def create_client(req: ClientCreate, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    ref = db.collection("offices").document(office_id).collection("clients").document()
    ref.set({
        "name": req.name,
        "code": req.code,
        "defaultTaxRate": req.default_tax_rate,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    return {"id": ref.id, "name": req.name}


# ---- 仕訳パターン管理 ----

class PatternCreate(BaseModel):
    keywords: list[str]
    vendor_name: str = ""
    debit_account: str
    debit_code: str = ""
    credit_account: str
    credit_code: str = ""
    tax_rate: str = "10"
    tax_category: str = ""
    description_template: str = ""


@app.get("/api/clients/{client_id}/patterns")
def list_patterns(client_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("patterns").stream()
    )
    patterns = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        patterns.append(d)
    return {"patterns": patterns}


@app.post("/api/clients/{client_id}/patterns")
def create_pattern(client_id: str, req: PatternCreate, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("patterns").document()
    )
    ref.set({
        "keywords": req.keywords,
        "vendorName": req.vendor_name,
        "debitAccount": req.debit_account,
        "debitCode": req.debit_code,
        "creditAccount": req.credit_account,
        "creditCode": req.credit_code,
        "taxRate": req.tax_rate,
        "taxCategory": req.tax_category,
        "descriptionTemplate": req.description_template,
    })
    return {"id": ref.id}


@app.delete("/api/clients/{client_id}/patterns/{pattern_id}")
def delete_pattern(client_id: str, pattern_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("patterns").document(pattern_id)
        .delete()
    )
    return {"ok": True}


# ---- レシートアップロード & 仕訳 ----

def _load_patterns(office_id: str, client_id: str) -> list[JournalPattern]:
    """Firestoreからクライアントの仕訳パターンを読み込み"""
    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("patterns").stream()
    )
    patterns = []
    for doc in docs:
        d = doc.to_dict()
        patterns.append(JournalPattern(
            id=doc.id,
            keywords=d.get("keywords", []),
            vendor_name=d.get("vendorName", ""),
            debit_account=d.get("debitAccount", ""),
            debit_code=d.get("debitCode", ""),
            credit_account=d.get("creditAccount", ""),
            credit_code=d.get("creditCode", ""),
            tax_rate=d.get("taxRate", "10"),
            tax_category=d.get("taxCategory", ""),
            description_template=d.get("descriptionTemplate", ""),
        ))
    return patterns


def _ocr_image(image_bytes: bytes) -> str:
    """Google Vision APIでOCRテキスト抽出"""
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)

    if response.text_annotations:
        return response.text_annotations[0].description
    return ""


def _extract_receipt_info(ocr_text: str) -> ReceiptData:
    """HaikuでOCRテキストからレシート情報を抽出"""
    import anthropic

    current_year = date_type.today().year
    ai_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    response = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""以下はレシート/領収書のOCRテキストです。情報を抽出してください。

--- OCRテキスト ---
{ocr_text[:3000]}
--- ここまで ---

■ 抽出ルール:
- vendor: 店名・会社名。一般的に通じる名称にする
- amount: 税込合計金額（「お預かり」「お釣り」は絶対に読まない）
- date: YYYY-MM-DD形式。現在{current_year}年前後
- invoiceNumber: T+13桁の登録番号。なければ空文字
- paymentMethod: "現金" or "カード"
  - クレジット/VISA/JCB/電子マネー/PayPay/Suica等 → "カード"
  - お釣り/釣銭の記載あり → "現金"
  - 不明 → "現金"
- taxRate: メインの税率。食品・飲料が主なら "8"、それ以外は "10"
  - ※マーク付き品目は軽減税率8%
- items: 主な品目名（最大5個）

{{"vendor": "店名", "amount": 数値, "date": "YYYY-MM-DD", "invoiceNumber": "", "paymentMethod": "現金", "taxRate": "10", "items": ["品目1", "品目2"]}}
JSONのみ返してください。""",
        }],
    )

    ai_text = response.content[0].text if response.content else ""
    json_match = re.search(r"\{[\s\S]*\}", ai_text)
    extracted = json.loads(json_match.group()) if json_match else {}

    return ReceiptData(
        vendor=extracted.get("vendor", "不明"),
        amount=int(extracted.get("amount", 0)),
        date=extracted.get("date", ""),
        invoice_number=extracted.get("invoiceNumber", ""),
        payment_method=extracted.get("paymentMethod", "現金"),
        tax_rate=extracted.get("taxRate", "10"),
        items=extracted.get("items", []),
        ocr_text=ocr_text,
    )


@app.post("/api/receipts/process")
async def process_receipt_upload(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    authorization: str = Header(...),
):
    """レシート画像をアップロード → OCR → 仕訳判定"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    # 画像読み込み
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "ファイルサイズは10MB以下にしてください")

    # 1. OCR
    print(f"[OCR] Processing {file.filename}...")
    ocr_text = _ocr_image(image_bytes)
    if not ocr_text:
        raise HTTPException(400, "OCRでテキストを読み取れませんでした")
    print(f"[OCR] Extracted {len(ocr_text)} chars")

    # 2. レシート情報抽出（Haiku）
    receipt = _extract_receipt_info(ocr_text)
    print(f"[抽出] {receipt.vendor} ¥{receipt.amount} {receipt.payment_method}")

    # 3. 仕訳パターン読み込み
    patterns = _load_patterns(office_id, client_id)

    # 4. 仕訳判定（Haiku → 必要ならOpus）
    entry = process_receipt(receipt, patterns)
    print(f"[仕訳] {entry.debit_account} / {entry.credit_account} confidence={entry.confidence}")

    # 5. Google Driveに画像保存
    client_doc = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id).get()
    )
    client_name = (client_doc.to_dict() or {}).get("name", "unknown")

    drive_file_id = ""
    drive_url = ""
    try:
        ext = os.path.splitext(file.filename or "")[1] or ".jpg"
        drive_filename = f"{receipt.date}_{receipt.vendor}_¥{receipt.amount}{ext}"
        drive_result = upload_receipt_to_drive(
            image_bytes=image_bytes,
            client_name=client_name,
            receipt_date=receipt.date,
            filename=drive_filename,
            payment_method=receipt.payment_method,
            content_type=file.content_type or "image/jpeg",
        )
        drive_file_id = drive_result.get("file_id", "")
        drive_url = drive_result.get("url", "")
        print(f"[Drive] Saved: {drive_url}")
    except Exception as e:
        print(f"[Drive] Upload failed: {e}")

    # 6. Firestoreに保存
    receipt_ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").document()
    )

    receipt_ref.set({
        "fileName": file.filename,
        "driveFileId": drive_file_id,
        "driveUrl": drive_url,
        "ocrText": ocr_text[:5000],
        "vendor": receipt.vendor,
        "amount": receipt.amount,
        "date": receipt.date,
        "invoiceNumber": receipt.invoice_number,
        "paymentMethod": receipt.payment_method,
        "taxRate": receipt.tax_rate,
        "items": receipt.items,
        "journal": {
            "debitAccount": entry.debit_account,
            "debitCode": entry.debit_code,
            "debitAmount": entry.debit_amount,
            "debitTaxCategory": entry.debit_tax_category,
            "creditAccount": entry.credit_account,
            "creditCode": entry.credit_code,
            "creditAmount": entry.credit_amount,
            "creditTaxCategory": entry.credit_tax_category,
            "taxRate": entry.tax_rate,
            "description": entry.description,
            "vendor": entry.vendor,
            "confidence": entry.confidence,
            "reasoning": entry.reasoning,
        },
        "status": "pending",
        "processedBy": uid,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })

    # 7. Google DriveのCSVにデータ追記
    try:
        append_to_csv(
            client_name=client_name,
            receipt_date=receipt.date,
            payment_method=receipt.payment_method,
            row_data={
                "date": receipt.date,
                "vendor": entry.vendor,
                "amount": receipt.amount,
                "debit_account": entry.debit_account,
                "credit_account": entry.credit_account,
                "tax_rate": f"{entry.tax_rate}%",
                "description": entry.description,
                "confidence": entry.confidence,
            },
        )
        print(f"[CSV] Appended to Drive CSV")
    except Exception as e:
        print(f"[CSV] Failed: {e}")

    return {
        "receiptId": receipt_ref.id,
        "receipt": {
            "vendor": receipt.vendor,
            "amount": receipt.amount,
            "date": receipt.date,
            "paymentMethod": receipt.payment_method,
            "taxRate": receipt.tax_rate,
            "items": receipt.items,
        },
        "journal": {
            "debitAccount": entry.debit_account,
            "debitCode": entry.debit_code,
            "debitAmount": entry.debit_amount,
            "creditAccount": entry.credit_account,
            "creditCode": entry.credit_code,
            "creditAmount": entry.credit_amount,
            "taxRate": entry.tax_rate,
            "description": entry.description,
            "vendor": entry.vendor,
            "confidence": entry.confidence,
            "reasoning": entry.reasoning,
        },
    }


# ---- 仕訳一覧 & 編集 ----

@app.get("/api/clients/{client_id}/receipts")
def list_receipts(client_id: str, authorization: str = Header(...)):
    """処理済みレシート＆仕訳一覧"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(200)
        .stream()
    )

    receipts = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        # Base64画像は一覧では返さない
        d.pop("imageBase64", None)
        d.pop("ocrText", None)
        receipts.append(d)

    return {"receipts": receipts}


class JournalUpdate(BaseModel):
    debit_account: str = ""
    debit_code: str = ""
    credit_account: str = ""
    credit_code: str = ""
    tax_rate: str = ""
    description: str = ""
    vendor: str = ""


@app.put("/api/clients/{client_id}/receipts/{receipt_id}")
def update_journal(
    client_id: str,
    receipt_id: str,
    req: JournalUpdate,
    authorization: str = Header(...),
):
    """仕訳の手動修正"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").document(receipt_id)
    )

    update_data = {"status": "edited"}
    if req.debit_account:
        update_data["journal.debitAccount"] = req.debit_account
    if req.debit_code:
        update_data["journal.debitCode"] = req.debit_code
    if req.credit_account:
        update_data["journal.creditAccount"] = req.credit_account
    if req.credit_code:
        update_data["journal.creditCode"] = req.credit_code
    if req.tax_rate:
        update_data["journal.taxRate"] = req.tax_rate
    if req.description:
        update_data["journal.description"] = req.description
    if req.vendor:
        update_data["journal.vendor"] = req.vendor

    ref.update(update_data)
    return {"ok": True}


@app.post("/api/clients/{client_id}/receipts/{receipt_id}/confirm")
def confirm_journal(
    client_id: str,
    receipt_id: str,
    authorization: str = Header(...),
):
    """仕訳を確定"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").document(receipt_id)
    )
    ref.update({"status": "confirmed"})
    return {"ok": True}


# ---- CSVエクスポート ----

@app.get("/api/clients/{client_id}/export")
def export_csv(
    client_id: str,
    format: str = "zaimu_ouen",  # zaimu_ouen / generic
    status: str = "confirmed",    # confirmed / all
    payment_method: str = "",     # 現金 / カード / 空=全部
    authorization: str = Header(...),
):
    """仕訳CSVダウンロード"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    query = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts")
    )

    if status != "all":
        query = query.where("status", "==", status)

    docs = query.stream()

    entries = []
    for doc in docs:
        d = doc.to_dict()
        j = d.get("journal", {})

        # 支払方法フィルタ
        if payment_method and d.get("paymentMethod", "") != payment_method:
            continue

        entries.append(JournalEntry(
            id=doc.id,
            entry_date=d.get("date", ""),
            debit_account=j.get("debitAccount", ""),
            debit_code=j.get("debitCode", ""),
            debit_amount=j.get("debitAmount", d.get("amount", 0)),
            debit_tax_category=j.get("debitTaxCategory", ""),
            credit_account=j.get("creditAccount", ""),
            credit_code=j.get("creditCode", ""),
            credit_amount=j.get("creditAmount", d.get("amount", 0)),
            credit_tax_category=j.get("creditTaxCategory", ""),
            tax_rate=j.get("taxRate", "10"),
            description=j.get("description", ""),
            vendor=j.get("vendor", d.get("vendor", "")),
            confidence=j.get("confidence", ""),
            reasoning=j.get("reasoning", ""),
        ))

    # 日付順ソート
    entries.sort(key=lambda e: e.entry_date)

    if format == "generic":
        csv_content = export_generic(entries)
        filename = "journal_entries.csv"
    else:
        csv_content = export_zaimu_ouen(entries)
        filename = "zaimu_ouen_import.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
