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
import drive_upload
from drive_upload import upload_receipt_to_drive, append_to_csv

app = FastAPI(title="記帳代行 仕訳API", version="0.2.0")

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


class InstructionsUpdate(BaseModel):
    instructions: str = ""


@app.get("/api/clients/{client_id}/instructions")
def get_instructions(client_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    doc = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id).get()
    )
    data = doc.to_dict() or {}
    return {"instructions": data.get("handwrittenInstructions", "")}


@app.put("/api/clients/{client_id}/instructions")
def update_instructions(client_id: str, req: InstructionsUpdate, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .update({"handwrittenInstructions": req.instructions})
    )
    return {"ok": True}


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


# ---- 仕訳ルール管理 ----

class RuleCreate(BaseModel):
    text: str


@app.get("/api/clients/{client_id}/rules")
def list_rules(client_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("rules")
        .order_by("createdAt")
        .stream()
    )
    rules = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        rules.append(d)
    return {"rules": rules}


@app.post("/api/clients/{client_id}/rules")
def create_rule(client_id: str, req: RuleCreate, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    if not req.text.strip():
        raise HTTPException(400, "ルールのテキストを入力してください")

    ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("rules").document()
    )
    ref.set({
        "text": req.text.strip(),
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    return {"id": ref.id, "text": req.text.strip()}


@app.delete("/api/clients/{client_id}/rules/{rule_id}")
def delete_rule(client_id: str, rule_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("rules").document(rule_id)
        .delete()
    )
    return {"ok": True}


# ---- 科目コードマスタ ----

class AccountCreate(BaseModel):
    code: str
    name: str


@app.get("/api/clients/{client_id}/accounts")
def list_accounts(client_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("accounts").stream()
    )
    accounts = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        accounts.append(d)
    return {"accounts": accounts}


@app.post("/api/clients/{client_id}/accounts")
def create_account(client_id: str, req: AccountCreate, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("accounts").document()
    )
    ref.set({
        "code": req.code,
        "name": req.name,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    return {"id": ref.id, "code": req.code, "name": req.name}


@app.delete("/api/clients/{client_id}/accounts/{account_id}")
def delete_account(client_id: str, account_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("accounts").document(account_id)
        .delete()
    )
    return {"ok": True}


@app.delete("/api/clients/{client_id}/accounts")
def delete_all_accounts(client_id: str, authorization: str = Header(...)):
    """科目コードマスタを全件削除"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("accounts").stream()
    )
    batch = db.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count % 500 == 0:
            batch.commit()
            batch = db.batch()
    if count % 500 != 0:
        batch.commit()
    return {"ok": True, "deleted": count}


# ---- 得意先マスタ ----

class CustomerCreate(BaseModel):
    name: str
    code: str = ""
    account: str = "売掛金"
    account_code: str = ""


@app.get("/api/clients/{client_id}/customers")
def list_customers(client_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("customers").stream()
    )
    customers = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        customers.append(d)
    return {"customers": customers}


@app.post("/api/clients/{client_id}/customers")
def create_customer(client_id: str, req: CustomerCreate, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("customers").document()
    )
    ref.set({
        "name": req.name,
        "code": req.code,
        "account": req.account,
        "accountCode": req.account_code,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    return {"id": ref.id, "name": req.name}


@app.delete("/api/clients/{client_id}/customers/{customer_id}")
def delete_customer(client_id: str, customer_id: str, authorization: str = Header(...)):
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("customers").document(customer_id)
        .delete()
    )
    return {"ok": True}


@app.delete("/api/clients/{client_id}/customers")
def delete_all_customers(client_id: str, authorization: str = Header(...)):
    """得意先マスタを全件削除"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("customers").stream()
    )
    batch = db.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count % 500 == 0:
            batch.commit()
            batch = db.batch()
    if count % 500 != 0:
        batch.commit()
    return {"ok": True, "deleted": count}


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


def _load_accounts(office_id: str, client_id: str) -> list[dict]:
    """Firestoreからクライアントの科目コードマスタを読み込み"""
    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("accounts").stream()
    )
    return [doc.to_dict() for doc in docs]


def _load_rules(office_id: str, client_id: str) -> list[str]:
    """Firestoreからクライアントの仕訳ルールを読み込み"""
    docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("rules")
        .order_by("createdAt")
        .stream()
    )
    return [doc.to_dict().get("text", "") for doc in docs]


def _ocr_image(image_bytes: bytes) -> str:
    """Google Vision APIでOCRテキスト抽出"""
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)

    if response.text_annotations:
        return response.text_annotations[0].description
    return ""


def _extract_receipt_info(ocr_text: str, is_handwritten: bool = False, image_bytes: bytes | None = None) -> tuple:
    """HaikuでOCRテキストからレシート情報を抽出。金額0なら画像で再試行"""
    import anthropic

    current_year = date_type.today().year
    ai_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    response = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""以下は{'手書きの領収書' if is_handwritten else 'レシート/領収書'}のOCRテキストです。情報を抽出してください。
{'※手書きのため読み取りにくい文字があります。文脈から推測してください。' if is_handwritten else ''}

--- OCRテキスト ---
{ocr_text[:3000]}
--- ここまで ---

■ 抽出ルール:
- vendor: 店名・会社名。一般的に通じる名称にする
- amount: 税込合計金額（「お預かり」「お釣り」は絶対に読まない）
- date: YYYY-MM-DD形式。現在{current_year}年（令和{current_year - 2018}年）前後
  - 和暦変換: 令和元年=2019, 令和2年=2020, ... 令和7年=2025, 令和8年=2026
  - 手書きで「R7」「R.7」「令7」等は令和7年=2025年
  - 年が不明・読めない場合は{current_year}年とする
- invoiceNumber: T+13桁の登録番号。なければ空文字
- paymentMethod: "現金" or "カード"
  - クレジット/VISA/JCB/電子マネー/PayPay/Suica等 → "カード"
  - お釣り/釣銭の記載あり → "現金"
  - 不明 → "現金"
- taxBreakdown: 税率ごとの内訳（重要！）
  - レシートに「8%対象」「10%対象」や「軽減税率対象」等の記載がある場合、それぞれの税込金額を抽出
  - ※マーク付き品目は軽減税率8%
  - 1種類の税率しかない場合は1要素だけ
- items: 主な品目名（最大5個）

以下のJSON形式で返してください:
{{"vendor": "店名", "amount": 合計金額, "date": "YYYY-MM-DD", "invoiceNumber": "", "paymentMethod": "現金", "taxBreakdown": [{{"taxRate": "10", "amount": 10対象金額}}, {{"taxRate": "8", "amount": 8対象金額}}], "items": ["品目1", "品目2"]}}

taxBreakdownは必ず配列で、税率が1種類でも配列にしてください。
JSONのみ返してください。""",
        }],
    )

    ai_text = response.content[0].text if response.content else ""
    json_match = re.search(r"\{[\s\S]*\}", ai_text)
    extracted = json.loads(json_match.group()) if json_match else {}

    # taxBreakdownから主要税率を判定
    tax_breakdown = extracted.get("taxBreakdown", [])
    if not tax_breakdown:
        main_tax_rate = "10"
    elif len(tax_breakdown) == 1:
        main_tax_rate = str(tax_breakdown[0].get("taxRate", "10"))
    else:
        # 金額が大きい方をメイン税率とする
        tax_breakdown.sort(key=lambda x: int(x.get("amount", 0)), reverse=True)
        main_tax_rate = str(tax_breakdown[0].get("taxRate", "10"))

    amount = int(extracted.get("amount") or 0)
    vendor = extracted.get("vendor", "不明")
    receipt_date = extracted.get("date", "")

    # 金額0 or 取引先不明 → 画像を直接Haikuに送って再抽出
    if image_bytes and (amount == 0 or vendor == "不明"):
        print(f"[抽出] OCRテキストから抽出不十分（金額={amount}, 取引先={vendor}）→ 画像で再抽出")
        try:
            img_b64 = base64.b64encode(image_bytes).decode("ascii")
            # content_typeを推測
            if image_bytes[:4] == b'\x89PNG':
                media_type = "image/png"
            elif image_bytes[:2] == b'\xff\xd8':
                media_type = "image/jpeg"
            else:
                media_type = "image/jpeg"

            vision_response = ai_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_b64},
                        },
                        {
                            "type": "text",
                            "text": f"""この{'手書きの領収書' if is_handwritten else 'レシート/領収書'}の画像から情報を読み取ってください。

■ 抽出ルール:
- vendor: 店名・会社名
- amount: 税込合計金額（数値のみ）
- date: YYYY-MM-DD形式。現在{current_year}年（令和{current_year - 2018}年）前後
  - 和暦変換: 令和7年=2025, 令和8年=2026。「R7」「令7」等も同様
  - 年が不明なら{current_year}年とする
- invoiceNumber: T+13桁の登録番号。なければ空文字
- paymentMethod: "現金" or "カード"
- items: 主な品目名（最大5個）

{{"vendor": "店名", "amount": 数値, "date": "YYYY-MM-DD", "invoiceNumber": "", "paymentMethod": "現金", "items": ["品目1"]}}
JSONのみ返してください。""",
                        },
                    ],
                }],
            )
            vision_text = vision_response.content[0].text if vision_response.content else ""
            vision_match = re.search(r"\{[\s\S]*\}", vision_text)
            if vision_match:
                vision_data = json.loads(vision_match.group())
                new_amount = int(vision_data.get("amount") or 0)
                new_vendor = vision_data.get("vendor", "")
                print(f"[抽出] 画像再抽出: 取引先={new_vendor}, 金額={new_amount}")
                if new_amount > 0:
                    amount = new_amount
                if new_vendor and new_vendor != "不明":
                    vendor = new_vendor
                if not receipt_date and vision_data.get("date"):
                    receipt_date = vision_data["date"]
                if not extracted.get("invoiceNumber") and vision_data.get("invoiceNumber"):
                    extracted["invoiceNumber"] = vision_data["invoiceNumber"]
                if not extracted.get("items") and vision_data.get("items"):
                    extracted["items"] = vision_data["items"]
        except Exception as e:
            print(f"[抽出] 画像再抽出エラー: {e}")

    return ReceiptData(
        vendor=vendor,
        amount=amount,
        date=receipt_date,
        invoice_number=extracted.get("invoiceNumber", ""),
        payment_method=extracted.get("paymentMethod", "現金"),
        tax_rate=main_tax_rate,
        items=extracted.get("items", []),
        ocr_text=ocr_text,
    ), tax_breakdown


@app.post("/api/receipts/upload")
async def upload_receipt_only(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    receipt_type: str = Form("receipt"),
    instructions: str = Form(""),
    authorization: str = Header(...),
):
    """レシート画像をDriveにアップロードのみ（OCR/仕訳は後で）"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "ファイルサイズは10MB以下にしてください")

    client_doc = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id).get()
    )
    client_name = (client_doc.to_dict() or {}).get("name", "unknown")

    # Google Driveに画像保存
    drive_file_id = ""
    drive_url = ""
    try:
        ext = os.path.splitext(file.filename or "")[1] or ".jpg"
        drive_filename = f"未処理_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        drive_result = upload_receipt_to_drive(
            image_bytes=image_bytes,
            client_name=client_name,
            receipt_date=datetime.now().strftime("%Y-%m-%d"),
            filename=drive_filename,
            payment_method="現金",
            content_type=file.content_type or "image/jpeg",
        )
        drive_file_id = drive_result.get("file_id", "")
        drive_url = drive_result.get("url", "")
    except Exception as e:
        print(f"[Drive] Upload failed: {e}")

    # Firestoreに未処理として保存（画像データもBase64で保存）
    receipt_ref = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").document()
    )
    receipt_ref.set({
        "fileName": file.filename,
        "driveFileId": drive_file_id,
        "driveUrl": drive_url,
        "contentType": file.content_type or "image/jpeg",
        "receiptType": receipt_type,
        "instructions": instructions,
        "status": "uploaded",
        "processedBy": uid,
        "createdAt": firestore.SERVER_TIMESTAMP,
    })

    return {
        "receiptId": receipt_ref.id,
        "fileName": file.filename,
        "driveUrl": drive_url,
        "status": "uploaded",
    }


@app.post("/api/clients/{client_id}/process-all")
def process_all_uploaded(
    client_id: str,
    receipt_type: str | None = None,
    authorization: str = Header(...),
):
    """未処理（uploaded）のレシートを一括OCR→仕訳判定"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    # uploaded状態のレシートを取得
    docs = list(
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts")
        .where("status", "==", "uploaded")
        .stream()
    )

    # receiptTypeでフィルタ
    if receipt_type:
        docs = [d for d in docs if (d.to_dict().get("receiptType", "receipt") == receipt_type)]

    if not docs:
        return {"processed": 0, "results": []}

    patterns = _load_patterns(office_id, client_id)
    rules = _load_rules(office_id, client_id)

    # 科目コードマスタを読み込み、ルールに追加
    accounts = _load_accounts(office_id, client_id)
    if accounts:
        account_lines = ["■ 科目コードマスタ（重要！この会社で使う勘定科目コードです。必ずこの中から選んでください）:"]
        for a in accounts:
            account_lines.append(f"- {a.get('code', '')} : {a.get('name', '')}")
        rules = list(rules) + ["\n".join(account_lines)]
        print(f"[科目コードマスタ] {len(accounts)}件")

    # 得意先マスタを読み込み、ルールに追加
    customer_docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("customers").stream()
    )
    customers = [d.to_dict() for d in customer_docs]

    # 補助コード→得意先名のマップ（摘要を補助と同じにするため）
    code_to_name = {}
    name_to_name = {}
    for c in customers:
        if c.get("code"):
            code_to_name[c["code"]] = c.get("name", "")
        if c.get("name"):
            name_to_name[c["name"]] = c.get("name", "")
    print(f"[得意先マスタ] {len(customers)}件, コードマップ: {code_to_name}")

    def _match_customer(entry: JournalEntry, code_map: dict, cust_list: list) -> dict | None:
        """仕訳のdebit_code/vendor/descriptionから得意先をマッチ。名前と補助コードを返す"""
        # 1. debit_codeで完全一致
        if entry.debit_code and entry.debit_code in code_map:
            print(f"[得意先マッチ] debit_code={entry.debit_code} → {code_map[entry.debit_code]}")
            return {"name": code_map[entry.debit_code], "code": entry.debit_code}

        # 法人格を除去して比較する関数
        def normalize(s: str) -> str:
            for w in ["株式会社", "有限会社", "合同会社", "㈱", "㈲", "(株)", "(有)", "（株）", "（有）"]:
                s = s.replace(w, "")
            return s.strip()

        vendor_norm = normalize(entry.vendor or "")
        desc_norm = normalize(entry.description or "")

        # 2. 正規化して部分一致
        for c in cust_list:
            cname = c.get("name", "")
            if not cname:
                continue
            cname_norm = normalize(cname)
            if (cname_norm and vendor_norm and
                (cname_norm in vendor_norm or vendor_norm in cname_norm or
                 cname_norm in desc_norm or desc_norm in cname_norm)):
                print(f"[得意先マッチ] 部分一致: {entry.vendor} → {cname} (補助:{c.get('code','')})")
                return {"name": cname, "code": c.get("code", "")}

        # 3. あいまいマッチ（共通文字数が7割以上、双方向で判定）
        for c in cust_list:
            cname = c.get("name", "")
            if not cname or len(cname) < 2:
                continue
            cname_norm = normalize(cname)
            if not vendor_norm or not cname_norm:
                continue
            # マスタ名→vendor方向
            common1 = sum(1 for ch in cname_norm if ch in vendor_norm)
            ratio1 = common1 / max(len(cname_norm), 1)
            # vendor→マスタ名方向
            common2 = sum(1 for ch in vendor_norm if ch in cname_norm)
            ratio2 = common2 / max(len(vendor_norm), 1)
            # どちらか高い方を採用
            ratio = max(ratio1, ratio2)
            if ratio >= 0.7:
                print(f"[得意先マッチ] あいまい({ratio:.0%}): {entry.vendor} → {cname} (補助:{c.get('code','')})")
                return {"name": cname, "code": c.get("code", "")}

        print(f"[得意先マッチ] マッチなし: debit_code={entry.debit_code}, vendor={entry.vendor}")
        return None

    def _apply_customer_match(entry: JournalEntry, matched: dict | None, cust_list: list):
        """得意先マッチ結果を仕訳の補助科目に反映（売掛金がある側に設定）"""
        if matched:
            name = matched["name"]
            code = matched.get("code", "")
            entry.description = name
            # 売掛金がどちら側にあるかを判定して補助を設定
            if "売掛" in entry.debit_account:
                entry.debit_sub_code = code
                entry.debit_sub_name = name
            elif "売掛" in entry.credit_account:
                entry.credit_sub_code = code
                entry.credit_sub_name = name
            else:
                # 売掛金がない場合は借方に設定
                entry.debit_sub_code = code
                entry.debit_sub_name = name
        elif cust_list:
            # 売掛金がある仕訳のみ「その他」を設定（レシート経費はvendorをそのまま使う）
            if "売掛" in entry.debit_account:
                entry.description = entry.vendor or "その他"
                entry.debit_sub_code = "その他"
                entry.debit_sub_name = "その他"
            elif "売掛" in entry.credit_account:
                entry.description = entry.vendor or "その他"
                entry.credit_sub_code = "その他"
                entry.credit_sub_name = "その他"

    if customers:
        customer_lines = ["""■ 得意先マスタ（重要！必ず以下のルールに従ってください）:
- OCRで読み取った取引先名と以下のマスタを照合してください
- 完全一致でなくてOK。7割程度一致していればそのマスタの補助科目を使ってください
  例: マスタ「株式会社山田工業」← OCR「(株)山田工業」「ヤマダコウギョウ」「山田工業㈱」→ 一致とみなす
  例: マスタ「田中商店」← OCR「タナカ商店」「田中ショウテン」→ 一致とみなす
- どのマスタにも当てはまらない場合は補助科目を「その他」にしてください
- 摘要（description）には、マッチした得意先マスタの「得意先名」をそのまま入れてください（補助科目と同じ名前）
- debit_codeには得意先の補助コードを入れてください"""]
        for c in customers:
            line = f"- {c.get('name', '')}"
            if c.get('code'):
                line += f" (補助コード: {c['code']})"
            line += f" → {c.get('account', '売掛金')}"
            if c.get('accountCode'):
                line += f"({c['accountCode']})"
            customer_lines.append(line)
        rules = list(rules) + ["\n".join(customer_lines)]

    client_doc = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id).get()
    )
    client_name = (client_doc.to_dict() or {}).get("name", "unknown")

    results = []
    for doc in docs:
        d = doc.to_dict()
        receipt_id = doc.id
        file_name = d.get("fileName", "不明")

        try:
            # Driveから画像を取得してOCR
            drive_fid = d.get("driveFileId", "")
            if not drive_fid:
                results.append({"receiptId": receipt_id, "fileName": file_name, "error": "Drive画像なし"})
                continue

            try:
                service = drive_upload._get_service()
                image_bytes = service.files().get_media(
                    fileId=drive_fid, supportsAllDrives=True
                ).execute()
            except Exception as e:
                results.append({"receiptId": receipt_id, "fileName": file_name, "error": f"Drive取得失敗: {e}"})
                continue
            ocr_text = _ocr_image(image_bytes)
            if not ocr_text:
                results.append({"receiptId": receipt_id, "fileName": file_name, "error": "OCR失敗"})
                continue

            # レシート情報抽出
            is_handwritten = d.get("receiptType", "receipt") == "handwritten"
            extra_instructions = d.get("instructions", "")
            receipt, tax_breakdown = _extract_receipt_info(ocr_text, is_handwritten=is_handwritten, image_bytes=image_bytes)

            # 追加指示がある場合、ルールに追加
            effective_rules = list(rules)
            if extra_instructions:
                effective_rules.append(extra_instructions)

            # Drive上のファイルをリネーム＆正しいフォルダに移動
            drive_file_id = d.get("driveFileId", "")
            if drive_file_id:
                try:
                    service = drive_upload._get_service()
                    ext = os.path.splitext(d.get("fileName", ""))[1] or ".jpg"
                    new_name = drive_upload._sanitize(
                        f"{receipt.date}_{receipt.vendor}_¥{receipt.amount}{ext}"
                    )

                    # 移動先フォルダを作成/取得: 顧問先/YYYY-MM/現金 or カード
                    dest_folder_id = None
                    if d.get("importedFromDrive"):
                        try:
                            # 処理月（今月）のフォルダに振り分け
                            current_month = datetime.now().strftime("%Y-%m")
                            client_folder_id = drive_upload._find_or_create_folder(
                                client_name, drive_upload.ROOT_FOLDER_ID
                            )
                            month_folder_id = drive_upload._find_or_create_folder(
                                current_month, client_folder_id
                            )
                            payment_folder = "カード" if receipt.payment_method == "カード" else "現金"
                            dest_folder_id = drive_upload._find_or_create_folder(
                                payment_folder, month_folder_id
                            )
                        except Exception as e:
                            print(f"[Drive] Folder creation failed: {e}")

                    # ファイルをコピー→元を削除で移動（共有ドライブ対応）
                    if dest_folder_id:
                        try:
                            # 新しいファイルとしてコピー
                            copied = service.files().copy(
                                fileId=drive_file_id,
                                body={"name": new_name, "parents": [dest_folder_id]},
                                supportsAllDrives=True,
                            ).execute()
                            # 元のファイルを削除
                            service.files().delete(
                                fileId=drive_file_id,
                                supportsAllDrives=True,
                            ).execute()
                            # FirestoreのdriveFileIdを新しいIDに更新
                            new_drive_id = copied["id"]
                            doc.reference.update({
                                "driveFileId": new_drive_id,
                                "driveUrl": f"https://drive.google.com/file/d/{new_drive_id}/view",
                            })
                            drive_file_id = new_drive_id
                            print(f"[Drive] Moved & renamed: {new_name} → {receipt.payment_method}/{receipt.date[:7]}")
                        except Exception as e:
                            print(f"[Drive] Move failed: {e}")
                            # 移動失敗してもリネームだけ試す
                            try:
                                service.files().update(
                                    fileId=drive_file_id,
                                    body={"name": new_name},
                                    supportsAllDrives=True,
                                ).execute()
                            except Exception:
                                pass
                    else:
                        # importedFromDriveでない場合は従来通りリネームのみ
                        service.files().update(
                            fileId=drive_file_id,
                            body={"name": new_name},
                            supportsAllDrives=True,
                        ).execute()
                except Exception as e:
                    print(f"[Drive] Rename/Move failed: {e}")

            # 税率分割対応
            entries_to_save = []
            if len(tax_breakdown) >= 2:
                for tb in tax_breakdown:
                    tb_rate = str(tb.get("taxRate", "10"))
                    tb_amount = int(tb.get("amount", 0))
                    if tb_amount <= 0:
                        continue
                    sub_receipt = ReceiptData(
                        vendor=receipt.vendor, amount=tb_amount,
                        date=receipt.date, invoice_number=receipt.invoice_number,
                        payment_method=receipt.payment_method, tax_rate=tb_rate,
                        items=receipt.items, ocr_text=receipt.ocr_text,
                    )
                    entry = process_receipt(sub_receipt, patterns, effective_rules)
                    _apply_customer_match(entry, _match_customer(entry, code_to_name, customers), customers)
                    entries_to_save.append((sub_receipt, entry, tb_rate))
            else:
                entry = process_receipt(receipt, patterns, effective_rules)
                _apply_customer_match(entry, _match_customer(entry, code_to_name, customers), customers)
                entries_to_save.append((receipt, entry, receipt.tax_rate))

            # 税率分割で全件スキップされた場合はフォールバック
            if not entries_to_save:
                entry = process_receipt(receipt, patterns, effective_rules)
                _apply_customer_match(entry, _match_customer(entry, code_to_name, customers), customers)
                entries_to_save.append((receipt, entry, receipt.tax_rate))

            # 元のドキュメントを更新（最初の仕訳）
            first_receipt, first_entry, first_rate = entries_to_save[0]
            doc.reference.update({
                "ocrText": ocr_text[:5000],
                "vendor": receipt.vendor,
                "amount": first_receipt.amount,
                "date": receipt.date,
                "invoiceNumber": receipt.invoice_number,
                "paymentMethod": receipt.payment_method,
                "taxRate": first_rate,
                "items": receipt.items,
                "journal": {
                    "debitAccount": first_entry.debit_account,
                    "debitCode": first_entry.debit_code,
                    "debitAmount": first_entry.debit_amount,
                    "debitTaxCategory": first_entry.debit_tax_category,
                    "debitSubCode": first_entry.debit_sub_code,
                    "debitSubName": first_entry.debit_sub_name,
                    "creditAccount": first_entry.credit_account,
                    "creditCode": first_entry.credit_code,
                    "creditAmount": first_entry.credit_amount,
                    "creditTaxCategory": first_entry.credit_tax_category,
                    "creditSubCode": first_entry.credit_sub_code,
                    "creditSubName": first_entry.credit_sub_name,
                    "taxRate": first_entry.tax_rate,
                    "description": first_entry.description,
                    "vendor": first_entry.vendor,
                    "confidence": first_entry.confidence,
                    "reasoning": first_entry.reasoning,
                },
                "status": "pending",
            })

            # 税率分割で2行目以降は新規ドキュメント
            for sub_receipt, entry, tax_rate in entries_to_save[1:]:
                new_ref = (
                    db.collection("offices").document(office_id)
                    .collection("clients").document(client_id)
                    .collection("receipts").document()
                )
                new_ref.set({
                    "fileName": d.get("fileName", ""),
                    "driveFileId": drive_file_id,
                    "driveUrl": d.get("driveUrl", ""),
                    "vendor": receipt.vendor,
                    "amount": sub_receipt.amount,
                    "date": receipt.date,
                    "invoiceNumber": receipt.invoice_number,
                    "paymentMethod": receipt.payment_method,
                    "taxRate": tax_rate,
                    "items": receipt.items,
                    "journal": {
                        "debitAccount": entry.debit_account,
                        "debitCode": entry.debit_code,
                        "debitAmount": entry.debit_amount,
                        "debitTaxCategory": entry.debit_tax_category,
                        "debitSubCode": entry.debit_sub_code,
                        "debitSubName": entry.debit_sub_name,
                        "creditAccount": entry.credit_account,
                        "creditCode": entry.credit_code,
                        "creditAmount": entry.credit_amount,
                        "creditTaxCategory": entry.credit_tax_category,
                        "creditSubCode": entry.credit_sub_code,
                        "creditSubName": entry.credit_sub_name,
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

            # CSV追記
            for sub_receipt, entry, _ in entries_to_save:
                try:
                    append_to_csv(
                        client_name=client_name,
                        receipt_date=receipt.date,
                        payment_method=receipt.payment_method,
                        row_data={
                            "date": receipt.date, "vendor": entry.vendor,
                            "amount": sub_receipt.amount,
                            "debit_account": entry.debit_account,
                            "credit_account": entry.credit_account,
                            "tax_rate": f"{entry.tax_rate}%",
                            "description": entry.description,
                            "confidence": entry.confidence,
                        },
                    )
                except Exception as e:
                    print(f"[CSV] Failed: {e}")

            results.append({
                "receiptId": receipt_id,
                "fileName": file_name,
                "vendor": receipt.vendor,
                "amount": receipt.amount,
                "entries": len(entries_to_save),
            })
            print(f"[処理完了] {file_name} → {receipt.vendor} ¥{receipt.amount}")

        except Exception as e:
            print(f"[処理エラー] {file_name}: {e}")
            results.append({"receiptId": receipt_id, "fileName": file_name, "error": str(e)})

    return {"processed": len(results), "results": results}


@app.post("/api/clients/{client_id}/import-from-drive")
def import_from_drive(
    client_id: str,
    authorization: str = Header(...),
):
    """Google Driveの「未処理」フォルダ内の画像をFirestoreに登録"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    # 顧問先名を取得
    client_doc = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id).get()
    )
    if not client_doc.exists:
        raise HTTPException(404, "顧問先が見つかりません")
    client_name = (client_doc.to_dict() or {}).get("name", "unknown")

    # 既にFirestoreに登録済みのDriveファイルIDを収集（重複防止）
    existing_drive_ids = set()
    existing_docs = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").stream()
    )
    for edoc in existing_docs:
        fid = edoc.to_dict().get("driveFileId", "")
        if fid:
            existing_drive_ids.add(fid)

    # Driveの顧問先フォルダ → 未処理フォルダを探す
    service = drive_upload._get_service()
    root_id = drive_upload.ROOT_FOLDER_ID

    safe_client_name = drive_upload._sanitize(client_name)
    q = (
        f"'{root_id}' in parents "
        f"and name = '{safe_client_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    result = service.files().list(q=q, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    client_folders = result.get("files", [])
    if not client_folders:
        return {"imported": 0, "skipped": 0, "message": f"Driveに「{client_name}」フォルダが見つかりません"}

    client_folder_id = client_folders[0]["id"]

    # 「未処理」フォルダを探す（なければ作成）
    unprocessed_folder_id = drive_upload._find_or_create_folder("未処理", client_folder_id)

    # 未処理フォルダ内の画像ファイルを取得
    image_mimes = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
    all_images = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{unprocessed_folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token,
        ).execute()
        for f in resp.get("files", []):
            if f["mimeType"] in image_mimes:
                all_images.append({
                    "id": f["id"],
                    "name": f["name"],
                    "mimeType": f["mimeType"],
                })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # 新規のみをFirestoreに登録
    imported = 0
    skipped = 0
    for img in all_images:
        if img["id"] in existing_drive_ids:
            skipped += 1
            continue

        receipt_ref = (
            db.collection("offices").document(office_id)
            .collection("clients").document(client_id)
            .collection("receipts").document()
        )
        receipt_ref.set({
            "fileName": img["name"],
            "driveFileId": img["id"],
            "driveUrl": f"https://drive.google.com/file/d/{img['id']}/view",
            "contentType": img["mimeType"],
            "receiptType": "receipt",
            "status": "uploaded",
            "processedBy": uid,
            "importedFromDrive": True,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
        imported += 1
        print(f"[Drive取込] {img['name']} → Firestore登録")

    return {
        "imported": imported,
        "skipped": skipped,
        "total_in_drive": len(all_images),
        "message": f"{imported}件取り込み、{skipped}件はスキップ（登録済み）",
    }


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
    receipt, tax_breakdown = _extract_receipt_info(ocr_text, image_bytes=image_bytes)
    print(f"[抽出] {receipt.vendor} ¥{receipt.amount} {receipt.payment_method} 税率内訳: {tax_breakdown}")

    # 3. 仕訳パターン & ルール読み込み
    patterns = _load_patterns(office_id, client_id)
    rules = _load_rules(office_id, client_id)

    # 科目コードマスタをルールに追加
    accounts = _load_accounts(office_id, client_id)
    if accounts:
        account_lines = ["■ 科目コードマスタ（重要！この会社で使う勘定科目コードです。必ずこの中から選んでください）:"]
        for a in accounts:
            account_lines.append(f"- {a.get('code', '')} : {a.get('name', '')}")
        rules = list(rules) + ["\n".join(account_lines)]

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

    # 4. 税率ごとに仕訳を生成（8%/10%混在対応）
    entries_to_save = []
    if len(tax_breakdown) >= 2:
        # 税率が複数ある → 税率ごとに仕訳を分ける
        for tb in tax_breakdown:
            tb_rate = str(tb.get("taxRate", "10"))
            tb_amount = int(tb.get("amount", 0))
            if tb_amount <= 0:
                continue
            sub_receipt = ReceiptData(
                vendor=receipt.vendor,
                amount=tb_amount,
                date=receipt.date,
                invoice_number=receipt.invoice_number,
                payment_method=receipt.payment_method,
                tax_rate=tb_rate,
                items=receipt.items,
                ocr_text=receipt.ocr_text,
            )
            entry = process_receipt(sub_receipt, patterns, rules)
            entries_to_save.append((sub_receipt, entry, tb_rate))
            print(f"[仕訳] {tb_rate}%分 ¥{tb_amount}: {entry.debit_account} / {entry.credit_account}")
    else:
        # 税率が1種類 → 通常処理
        entry = process_receipt(receipt, patterns, rules)
        entries_to_save.append((receipt, entry, receipt.tax_rate))
        print(f"[仕訳] {entry.debit_account} / {entry.credit_account} confidence={entry.confidence}")

    # 6. Firestoreに保存（税率分割分も含む）
    saved_entries = []
    for sub_receipt, entry, tax_rate in entries_to_save:
        receipt_ref = (
            db.collection("offices").document(office_id)
            .collection("clients").document(client_id)
            .collection("receipts").document()
        )

        receipt_ref.set({
            "fileName": file.filename,
            "driveFileId": drive_file_id,
            "driveUrl": drive_url,
            "ocrText": ocr_text[:5000] if len(saved_entries) == 0 else "",
            "vendor": receipt.vendor,
            "amount": sub_receipt.amount,
            "date": receipt.date,
            "invoiceNumber": receipt.invoice_number,
            "paymentMethod": receipt.payment_method,
            "taxRate": tax_rate,
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

        saved_entries.append({
            "receiptId": receipt_ref.id,
            "amount": sub_receipt.amount,
            "taxRate": tax_rate,
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
                    "amount": sub_receipt.amount,
                    "debit_account": entry.debit_account,
                    "credit_account": entry.credit_account,
                    "tax_rate": f"{entry.tax_rate}%",
                    "description": entry.description,
                    "confidence": entry.confidence,
                },
            )
        except Exception as e:
            print(f"[CSV] Failed: {e}")

    first = saved_entries[0] if saved_entries else {}
    return {
        "receiptId": first.get("receiptId", ""),
        "receipt": {
            "vendor": receipt.vendor,
            "amount": receipt.amount,
            "date": receipt.date,
            "paymentMethod": receipt.payment_method,
            "taxRate": receipt.tax_rate,
            "invoiceNumber": receipt.invoice_number,
            "items": receipt.items,
        },
        "journal": first.get("journal", {}),
        "entries": saved_entries,
        "taxSplit": len(saved_entries) > 1,
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
    amount: int | None = None


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
    if req.amount is not None:
        update_data["amount"] = req.amount
        update_data["journal.debitAmount"] = req.amount
        update_data["journal.creditAmount"] = req.amount

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


@app.delete("/api/clients/{client_id}/receipts/{receipt_id}")
def delete_receipt(
    client_id: str,
    receipt_id: str,
    authorization: str = Header(...),
):
    """レシート・仕訳を削除"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").document(receipt_id)
        .delete()
    )
    return {"ok": True}


@app.delete("/api/clients/{client_id}/receipts/errors")
def delete_error_receipts(
    client_id: str,
    authorization: str = Header(...),
):
    """仕訳データがないレシート（エラー分）を一括削除"""
    uid = verify_token(authorization)
    office_id = get_office_id(uid)

    receipts = (
        db.collection("offices").document(office_id)
        .collection("clients").document(client_id)
        .collection("receipts").stream()
    )

    deleted = 0
    for doc in receipts:
        d = doc.to_dict()
        journal = d.get("journal")
        if not journal or not journal.get("debitAccount"):
            doc.reference.delete()
            deleted += 1

    return {"ok": True, "deleted": deleted}


# ---- CSVエクスポート ----

@app.get("/api/clients/{client_id}/export")
def export_csv(
    client_id: str,
    format: str = "zaimu_ouen",  # zaimu_ouen / generic
    status: str = "confirmed",    # confirmed / all
    payment_method: str = "",     # 現金 / カード / 空=全部
    date_from: str = "",          # 日付範囲（開始）YYYY-MM-DD
    date_to: str = "",            # 日付範囲（終了）YYYY-MM-DD
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

    entries_with_ts = []
    for doc in docs:
        d = doc.to_dict()
        j = d.get("journal", {})

        # 支払方法フィルタ
        if payment_method and d.get("paymentMethod", "") != payment_method:
            continue

        # アップロード日範囲フィルタ（createdAt基準）
        created_at = d.get("createdAt")
        if created_at and (date_from or date_to):
            if hasattr(created_at, 'strftime'):
                created_str = created_at.strftime("%Y-%m-%d")
            else:
                created_str = str(created_at)[:10]
            if date_from and created_str < date_from:
                continue
            if date_to and created_str > date_to:
                continue

        entry = JournalEntry(
            id=doc.id,
            entry_date=d.get("date", ""),
            debit_account=j.get("debitAccount", ""),
            debit_code=j.get("debitCode", ""),
            debit_amount=j.get("debitAmount", d.get("amount", 0)),
            debit_tax_category=j.get("debitTaxCategory", ""),
            debit_sub_code=j.get("debitSubCode", ""),
            debit_sub_name=j.get("debitSubName", ""),
            credit_account=j.get("creditAccount", ""),
            credit_code=j.get("creditCode", ""),
            credit_amount=j.get("creditAmount", d.get("amount", 0)),
            credit_tax_category=j.get("creditTaxCategory", ""),
            credit_sub_code=j.get("creditSubCode", ""),
            credit_sub_name=j.get("creditSubName", ""),
            tax_rate=j.get("taxRate", "10"),
            description=j.get("description", ""),
            vendor=j.get("vendor", d.get("vendor", "")),
            confidence=j.get("confidence", ""),
            reasoning=j.get("reasoning", ""),
        )
        # ソート用にcreatedAtを保持
        entries_with_ts.append((created_at, entry))

    # 取り込み順（createdAt昇順）でソート
    entries_with_ts.sort(key=lambda x: x[0] if x[0] else "")
    entries = [e for _, e in entries_with_ts]

    # 取り込み順ソート（createdAt基準）
    # entries はドキュメント順に追加されているのでそのまま

    # 同日・同金額の重複チェック（除外はせずフラグを立てる）
    from collections import Counter
    date_amount_count = Counter()
    for e in entries:
        key = (e.entry_date, e.debit_amount)
        date_amount_count[key] += 1
    for e in entries:
        key = (e.entry_date, e.debit_amount)
        if date_amount_count[key] >= 2:
            e.duplicate_flag = "※重複?"

    if format == "generic":
        csv_content = export_generic(entries)
        filename = "journal_entries.csv"
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        csv_bytes = export_zaimu_ouen(entries)
        filename = "zaimu_ouen_import.csv"
        return StreamingResponse(
            iter([csv_bytes]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
