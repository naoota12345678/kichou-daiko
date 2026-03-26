"""スクレイピングAPI — Cloud Run用FastAPIサーバー

Webアプリ (Vercel) → このAPI → EC各サイトスクレイピング → Google Drive保存
"""

from __future__ import annotations

import base64
import io
import json
import os
from decimal import Decimal
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials, firestore
import asyncio

from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from browser_session import BrowserSession
from scrapers.amazon_scraper import scrape_amazon
from scrapers.rakuten_scraper import scrape_rakuten
from scrapers.yahoo_scraper import scrape_yahoo
from scrapers.amazon_receipt import download_receipts as download_amazon_receipts
from scrapers.rakuten_receipt import download_receipts as download_rakuten_receipts
from drive_helper import upload_receipt_and_update_csv

app = FastAPI(title="acc-tool Scraper API")

# CORS: Vercelドメインからのリクエストを許可
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "https://dentyo.romu.ai").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Firebase Admin初期化
if not firebase_admin._apps:
    if os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"):
        sa = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])
        cred = credentials.Certificate(sa)
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

db = firestore.client()


def verify_token(authorization: str) -> str:
    """Firebase ID tokenを検証してuidを返す"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")
    token = authorization[7:]
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")


def get_user_session(uid: str, site: str) -> dict | None:
    """Firestoreからセッション情報を取得"""
    doc = db.collection("users").document(uid).collection("sessions").document(site).get()
    return doc.to_dict() if doc.exists else None


def save_user_session(uid: str, site: str, session_data: dict):
    """Firestoreにセッション情報を保存"""
    db.collection("users").document(uid).collection("sessions").document(site).set(session_data)


def get_drive_tokens(uid: str) -> dict | None:
    """FirestoreからDriveトークンを取得"""
    doc = db.collection("users").document(uid).collection("private").document("tokens").get()
    return doc.to_dict() if doc.exists else None


class ScrapeRequest(BaseModel):
    site: str  # amazon / rakuten / yahoo
    year: int | None = None
    download_receipts: bool = True


class ScrapeResponse(BaseModel):
    items: list[dict]
    uploaded_files: list[str]
    errors: list[str]


class SessionCheckRequest(BaseModel):
    site: str


class SaveSessionRequest(BaseModel):
    site: str
    cookies: list[dict]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/save-session")
def save_session(
    req: SaveSessionRequest,
    authorization: str = Header(...),
):
    """Chrome拡張から送信されたcookieをFirestoreに保存"""
    uid = verify_token(authorization)

    # Playwright storage_state形式に変換
    storage_state = {
        "cookies": req.cookies,
        "origins": [],
    }
    save_user_session(uid, req.site, {"storage_state": storage_state})
    return {"ok": True, "site": req.site, "cookie_count": len(req.cookies)}


@app.post("/api/check-session")
def check_session(
    req: SessionCheckRequest,
    authorization: str = Header(...),
):
    """指定サイトのセッションが有効か確認"""
    uid = verify_token(authorization)
    session = get_user_session(uid, req.site)
    return {"has_session": session is not None}


@app.post("/api/scrape", response_model=ScrapeResponse)
def scrape(
    req: ScrapeRequest,
    authorization: str = Header(...),
):
    """EC サイトをスクレイピングしてDriveに保存"""
    uid = verify_token(authorization)

    # ユーザー設定取得
    user_doc = db.collection("users").document(uid).get()
    user_data = user_doc.to_dict() or {}
    fiscal_year_start_month = user_data.get("fiscalYearStartMonth", 1)
    root_folder_id = user_data.get("driveRootFolderId", "")

    # セッション取得 (保存済みPlaywrightストレージステート)
    session = get_user_session(uid, req.site)
    session_path = Path(f"/tmp/{uid}_{req.site}_session.json")
    if session and session.get("storage_state"):
        session_path.write_text(json.dumps(session["storage_state"]))

    # スクレイピング実行
    errors: list[str] = []
    items = []

    try:
        if req.site == "amazon":
            # セッションファイルを設定
            from scrapers import amazon_scraper
            amazon_scraper.STATE_FILE = session_path
            result = scrape_amazon(year=req.year, headless=True)
            items = result.items
            errors.extend(result.errors)

        elif req.site == "rakuten":
            from scrapers import rakuten_scraper
            rakuten_scraper.STATE_FILE = session_path
            result = scrape_rakuten(year=req.year, headless=True)
            items = result.items
            errors.extend(result.errors)

        elif req.site == "yahoo":
            from scrapers import yahoo_scraper
            yahoo_scraper.STATE_FILE = session_path
            result = scrape_yahoo(year=req.year, headless=True)
            items = result.items
            errors.extend(result.errors)

        else:
            raise HTTPException(400, f"Unknown site: {req.site}")

    except Exception as e:
        errors.append(f"Scraping failed: {e}")

    # セッション保存 (次回再利用)
    if session_path.exists():
        storage_state = json.loads(session_path.read_text())
        save_user_session(uid, req.site, {"storage_state": storage_state})

    # Drive にアップロード (旧API - 互換用)
    uploaded_files: list[str] = []
    if items and root_folder_id:
        try:
            pass  # 新方式はWebSocket経由で実行
        except Exception as e:
            errors.append(f"Drive upload failed: {e}")

    # OrderItemをdict化
    items_dicts = [
        {
            "orderDate": item.order_date.isoformat(),
            "vendor": item.vendor,
            "productName": item.product_name,
            "amount": int(item.amount),
            "invoiceNumber": item.invoice_number,
            "source": item.source.value if hasattr(item.source, 'value') else str(item.source),
            "orderId": item.order_id,
        }
        for item in items
    ]

    return ScrapeResponse(
        items=items_dicts,
        uploaded_files=uploaded_files,
        errors=errors,
    )


# ---- ウォームアップ ----

@app.post("/api/warmup")
def warmup():
    """Cloud Runウォームアップ（コールドスタート回避）"""
    return {"status": "warm"}


# ---- レシートOCR処理 (Cloud Run) ----

class ProcessReceiptsRequest(BaseModel):
    receiptType: str = ""  # 未使用（自動判定）


@app.post("/api/process-receipts")
def process_receipts(
    authorization: str = Header(...),
):
    """未処理レシートを一括OCR → リネーム → 振り分け → CSV追記"""
    import anthropic
    from datetime import date as date_type

    uid = verify_token(authorization)

    user_doc = db.collection("users").document(uid).get()
    user_data = user_doc.to_dict() or {}
    root_folder_id = user_data.get("driveRootFolderId", "")
    fiscal_year_start_month = user_data.get("fiscalYearStartMonth", 1)

    if not root_folder_id:
        raise HTTPException(400, "Drive未設定")

    drive_tokens = get_drive_tokens(uid)
    if not drive_tokens or not drive_tokens.get("driveRefreshToken"):
        raise HTTPException(400, "Driveトークン未設定")

    from drive_helper import _get_credentials, _ensure_folder, _find_file
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaInMemoryUpload

    creds = _get_credentials(drive_tokens["driveRefreshToken"])
    service = build("drive", "v3", credentials=creds)

    # 未処理フォルダ検索
    query = (
        f"name='未処理' and '{root_folder_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    res = service.files().list(q=query, fields="files(id)").execute()
    temp_folders = res.get("files", [])
    if not temp_folders:
        return {"processed": 0, "message": "未処理フォルダがありません"}

    temp_folder_id = temp_folders[0]["id"]

    # 未処理ファイル一覧
    files_res = service.files().list(
        q=f"'{temp_folder_id}' in parents and trashed=false",
        fields="files(id,name,mimeType)",
        pageSize=100,
    ).execute()
    unprocessed = files_res.get("files", [])

    if not unprocessed:
        return {"processed": 0, "message": "未処理ファイルはありません"}

    # Firestoreにジョブ作成
    job_ref = db.collection("users").document(uid).collection("receipt_jobs").document()
    job_ref.set({
        "status": "processing",
        "total": len(unprocessed),
        "processed": 0,
        "results": [],
        "createdAt": firestore.SERVER_TIMESTAMP,
    })

    # アップロード日 = 今日 → フォルダは今月
    now = date_type.today()
    upload_year = now.year
    upload_month = now.month
    upload_fiscal_year = upload_year - 1 if upload_month < fiscal_year_start_month else upload_year

    year_folder_id = _ensure_folder(service, f"{upload_fiscal_year}年度", root_folder_id)
    month_folder_id = _ensure_folder(service, f"{upload_month}月", year_folder_id)
    card_folder_id = _ensure_folder(service, "カード領収書", month_folder_id)
    cash_folder_id = _ensure_folder(service, "現金領収書", month_folder_id)

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    current_year = now.year

    results = []
    card_csv_rows = []
    cash_csv_rows = []

    for i, file in enumerate(unprocessed):
        try:
            # ファイルダウンロード
            content = service.files().get_media(fileId=file["id"]).execute()

            # Google Vision OCR でテキスト抽出
            from google.cloud import vision as gvision
            vision_client = gvision.ImageAnnotatorClient()

            file_ext = file["name"].rsplit(".", 1)[-1].lower() if "." in file["name"] else ""
            if file_ext == "pdf":
                # PDFの場合: 高解像度で画像に変換してからOCR
                import fitz  # PyMuPDF
                from PIL import Image, ImageEnhance
                import io
                pdf_doc = fitz.open(stream=content, filetype="pdf")
                ocr_text = ""
                for page in pdf_doc:
                    pix = page.get_pixmap(dpi=300)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    # コントラスト強調で薄い文字を読みやすくする
                    img = ImageEnhance.Contrast(img).enhance(1.5)
                    img = ImageEnhance.Sharpness(img).enhance(2.0)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    img_bytes = buf.getvalue()
                    vision_image = gvision.Image(content=img_bytes)
                    vision_response = vision_client.text_detection(image=vision_image)
                    if vision_response.text_annotations:
                        ocr_text += vision_response.text_annotations[0].description + "\n"
                pdf_doc.close()
            else:
                vision_image = gvision.Image(content=content)
                vision_response = vision_client.text_detection(image=vision_image)
                ocr_text = vision_response.text_annotations[0].description if vision_response.text_annotations else ""
            # PDFの場合、Claude用の画像も準備
            receipt_image_b64 = None
            if file_ext == "pdf":
                import fitz as fitz2
                import io as io2
                pdf_for_img = fitz2.open(stream=content, filetype="pdf")
                if len(pdf_for_img) > 0:
                    pix2 = pdf_for_img[0].get_pixmap(dpi=200)
                    receipt_image_b64 = base64.b64encode(pix2.tobytes("png")).decode()
                pdf_for_img.close()
            elif file_ext in ("jpg", "jpeg", "png", "webp"):
                receipt_image_b64 = base64.b64encode(content).decode()

            print(f"[OCR] Vision text ({len(ocr_text)} chars): {ocr_text[:100]}...")

            # Haiku でテキスト+画像を解析
            msg_content = []
            if receipt_image_b64:
                media_type = "image/png" if file_ext == "pdf" else (f"image/{file_ext}" if file_ext in ("png", "webp") else "image/jpeg")
                msg_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": receipt_image_b64},
                })
            msg_content.append({
                "type": "text",
                "text": f"""以下はレシート/領収書のOCRテキストです。画像も添付しています。OCRテキストが不十分な場合は画像から直接読み取ってください。

--- OCRテキスト ---
{ocr_text[:3000]}
--- ここまで ---

■ 店名（vendor）:
- テキストの最初の方にある店名・会社名を読み取る
- 正式名称ではなく、一般的に通じる店名にする（例：「株式会社ツルハ」→「ツルハドラッグ」）
- 駐車場のレシートも店名を読む（例：タイムズ24、三井のリパーク等）

■ 金額（amount）:
- 「合計」「お買上合計」「税込合計」「ご請求額」「お支払い合計」の金額を読む
- 駐車場の場合は「駐車料金」「利用料金」の金額を読む
- 「お預かり」「預かり現金」「お釣り」「釣銭」は絶対に読まない。これは支払額ではない
- 「小計」より「合計」を優先。最終的な税込支払金額を選ぶ

■ 支払方法（paymentMethod）:
- テキスト全体を見て、特に後半の支払情報を確認する
- 以下のいずれかの記載があれば → "カード":
  クレジット, CREDIT, カード払い, VISA, Mastercard, JCB, AMEX, Diners,
  電子マネー, QUICPay, iD, Suica, PASMO, nanaco, WAON, 楽天Edy,
  PayPay, d払い, 楽天ペイ, au PAY, メルペイ, LINE Pay,
  タッチ決済, コンタクトレス, contactless
- 「お釣り」「釣銭」の記載があれば → "現金"（お預かりだけでは判定しない。カードでもお預かりはある）
- 上記どちらにも該当しない場合 → "現金"

■ 日付（date）:
- 現在{current_year}年前後。{current_year - 5}年以前にはならない

■ インボイス番号（invoiceNumber）:
- T+13桁の登録番号。なければ空文字

■ 確信度（confidence）:
- "low"にするのは本当に読めない場合だけ:
  店名が全く読めない、金額が複数あり確定できない、日付が見つからない等
- 多少読みにくくても判読できたなら → "high"

{{"amount": 数値, "vendor": "店名", "date": "YYYY-MM-DD", "invoiceNumber": "T+13桁or空文字", "paymentMethod": "現金"or"カード", "confidence": "high"or"low"}}
JSONのみ返してください。"""
            })
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": msg_content}],
            )

            ai_text = response.content[0].text if response.content[0].type == "text" else ""
            json_match = __import__("re").search(r"\{[\s\S]*\}", ai_text)
            extracted = json.loads(json_match.group()) if json_match else {}

            amount = extracted.get("amount", 0)
            vendor = extracted.get("vendor", "不明")
            receipt_date = extracted.get("date", "")
            invoice_number = extracted.get("invoiceNumber", "")
            payment_method = extracted.get("paymentMethod", "現金")
            confidence = extracted.get("confidence", "low")

            # 年の妥当性チェック
            if receipt_date:
                try:
                    y = int(receipt_date.split("-")[0])
                    if y < current_year - 2 or y > current_year + 1:
                        receipt_date = f"{current_year}-{receipt_date.split('-')[1]}-{receipt_date.split('-')[2]}"
                except Exception:
                    pass

            # ファイル名生成
            import unicodedata
            date_str = receipt_date.replace("-", "") if receipt_date else now.strftime("%Y%m%d")
            clean_vendor = unicodedata.normalize("NFKC", vendor)
            clean_vendor = __import__("re").sub(r'[\\/:*?"<>|\n\r\t]', "", clean_vendor)[:20].strip()
            ext = "." + file["name"].rsplit(".", 1)[-1] if "." in file["name"] else ".jpg"
            new_name = f"{date_str}_{clean_vendor}_{amount}"
            if invoice_number:
                new_name += f"_{invoice_number}"
            new_name += ext

            # フォルダ移動 + リネーム
            target_folder = card_folder_id if payment_method == "カード" else cash_folder_id
            service.files().update(
                fileId=file["id"],
                addParents=target_folder,
                removeParents=temp_folder_id,
                body={"name": new_name},
            ).execute()

            # confidence=lowなら「要確認」フォルダにもコピー
            if confidence == "low":
                review_folder_id = _ensure_folder(service, "要確認", root_folder_id)
                service.files().copy(
                    fileId=file["id"],
                    body={"name": new_name, "parents": [review_folder_id]},
                ).execute()

            result = {
                "oldName": file["name"],
                "newName": new_name,
                "amount": amount,
                "vendor": vendor,
                "date": receipt_date,
                "invoiceNumber": invoice_number,
                "paymentMethod": payment_method,
                "confidence": confidence,
            }
            results.append(result)

            # CSV行
            row = {"date": receipt_date, "vendor": vendor, "amount": str(amount), "invoiceNumber": invoice_number}
            if payment_method == "カード":
                card_csv_rows.append(row)
            else:
                cash_csv_rows.append(row)

            print(f"[OCR] [{i+1}/{len(unprocessed)}] {new_name} ¥{amount} {'💳' if payment_method == 'カード' else '💴'}")

        except Exception as e:
            print(f"[OCR] [{i+1}/{len(unprocessed)}] Error: {e}")
            results.append({"oldName": file["name"], "error": str(e)})

        # 進捗更新
        job_ref.update({"processed": i + 1, "results": results})

    # CSV追記
    if card_csv_rows:
        _append_csv(service, month_folder_id, "カード.csv", card_csv_rows)
    if cash_csv_rows:
        _append_csv(service, month_folder_id, "現金.csv", cash_csv_rows)

    # dedupコレクションをクリア（処理済みファイルのロックを解放）
    dedup_docs = db.collection("users").document(uid).collection("upload_dedup").stream()
    for ddoc in dedup_docs:
        ddoc.reference.delete()

    # ジョブ完了
    job_ref.update({"status": "complete", "results": results})

    return {"processed": len(results), "results": results}


def _append_csv(service, folder_id: str, csv_name: str, rows: list[dict]):
    """DriveのCSVに行を追記"""
    import csv as csv_mod
    import io

    # 既存CSV検索
    query = f"name='{csv_name}' and '{folder_id}' in parents and trashed=false"
    res = service.files().list(q=query, fields="files(id)").execute()
    existing = res.get("files", [])

    content = ""
    if existing:
        try:
            content = service.files().get_media(fileId=existing[0]["id"]).execute().decode("utf-8-sig")
        except Exception:
            pass

    if not content:
        content = "日付,取引先,金額,インボイス番号\n"

    for row in rows:
        content += f"{row['date']},{row['vendor']},{row['amount']},{row['invoiceNumber']}\n"

    from googleapiclient.http import MediaInMemoryUpload
    media = MediaInMemoryUpload(content.encode("utf-8-sig"), mimetype="text/csv")

    if existing:
        service.files().update(fileId=existing[0]["id"], media_body=media).execute()
    else:
        meta = {"name": csv_name, "parents": [folder_id]}
        service.files().create(body=meta, media_body=media, fields="id").execute()

    print(f"[CSV] {csv_name}: {len(rows)} rows added")


import base64

# ---- リモートブラウザ (WebSocket) ----


@app.websocket("/api/browser/ws")
async def browser_ws(websocket: WebSocket):
    """WebSocketでブラウザ画面をストリーミング（パラメータはクエリで受取）"""
    await websocket.accept()

    # クエリパラメータからセッション情報取得
    token = websocket.query_params.get("token", "")
    site = websocket.query_params.get("site", "amazon")
    year_str = websocket.query_params.get("year", "")
    year = int(year_str) if year_str else None

    # トークン検証
    try:
        uid = verify_token(f"Bearer {token}")
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Auth failed: {e}"})
        await websocket.close()
        return

    session = BrowserSession(site=site, year=year)
    stream_task = None

    try:
        # ブラウザ起動
        print("[WS] Starting browser...")
        await websocket.send_json({"type": "status", "status": "starting"})
        await session.start()
        print("[WS] Browser ready")
        await websocket.send_json({"type": "status", "status": "ready"})

        ws_alive = True

        # スクリーンショット配信タスク
        async def stream_screenshots():
            nonlocal ws_alive
            while session._running and ws_alive:
                try:
                    jpeg = await session.capture_screenshot()
                    if jpeg and ws_alive:
                        await websocket.send_bytes(jpeg)
                except (WebSocketDisconnect, Exception):
                    ws_alive = False
                    return
                await asyncio.sleep(0.15)

        # ログイン検出タスク（WebSocket切断後も継続）
        async def detect_login():
            for _ in range(150):  # 最大5分待機
                try:
                    if await session.check_login():
                        print("[WS] Login detected!")
                        return True
                except Exception as e:
                    print(f"[WS] Login check error: {e}")
                await asyncio.sleep(2)
            print("[WS] Login detection timeout")
            return False

        stream_task = asyncio.create_task(stream_screenshots())
        login_task = asyncio.create_task(detect_login())

        # Firestoreにジョブを先に作成（クライアントが監視開始できるように）
        job_ref = db.collection("users").document(uid).collection("jobs").document()
        job_id = job_ref.id
        job_ref.set({
            "status": "waiting_login",
            "site": site,
            "year": year,
            "items": [],
            "uploadedFiles": [],
            "error": "",
            "createdAt": firestore.SERVER_TIMESTAMP,
        })

        try:
            await websocket.send_json({"type": "status", "status": "ready", "jobId": job_id})
        except Exception:
            pass

        # ユーザー入力の受信ループ
        while session._running and ws_alive:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                msg = json.loads(data)

                if msg.get("type") == "click":
                    await session.dispatch_mouse("click", msg["x"], msg["y"])
                elif msg.get("type") == "key":
                    await session.dispatch_key(msg["key"], msg.get("event", "keyDown"))
                elif msg.get("type") == "insertText":
                    await session.insert_text(msg["text"])
                elif msg.get("type") == "focusInput":
                    await session.focus_input()
                elif msg.get("type") == "scroll":
                    if session.cdp_session:
                        try:
                            await session.cdp_session.send(
                                "Input.dispatchMouseEvent",
                                {
                                    "type": "mouseWheel",
                                    "x": msg.get("x", 195),
                                    "y": msg.get("y", 422),
                                    "deltaX": msg.get("deltaX", 0),
                                    "deltaY": msg.get("deltaY", 0),
                                },
                            )
                        except Exception:
                            pass
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                print("[WS] Client disconnected, continuing login detection...")
                ws_alive = False
                break
            except Exception as e:
                print(f"[WS] Input error: {e}")

            # ログイン検出チェック
            if login_task.done():
                break

        # WebSocket切断してもログイン検出を待つ
        if not login_task.done():
            print("[WS] Waiting for login detection (client disconnected)...")
            login_detected = await login_task
        else:
            try:
                login_detected = login_task.result()
            except Exception:
                login_detected = False

        # スクリーンショット停止
        stream_task.cancel()
        try:
            await stream_task
        except (asyncio.CancelledError, Exception):
            pass

        if login_detected:
            print("[WS] Starting scrape...")
            job_ref.update({"status": "scraping"})

            try:
                await websocket.send_json({"type": "status", "status": "scraping", "jobId": job_id})
            except Exception:
                print("[WS] Client disconnected, scraping continues in background")

            # スクリーンショット停止
            session._running = False
            if stream_task:
                stream_task.cancel()
                try:
                    await stream_task
                except (asyncio.CancelledError, Exception):
                    pass

            # スクレイピング実行
            try:
                items = await session.scrape()
                print(f"[WS] Scrape complete: {len(items)} items")
            except Exception as e:
                print(f"[WS] Scrape error: {e}")
                import traceback
                traceback.print_exc()
                items = []
                job_ref.update({"status": "error", "error": str(e)})

            # 領収書PDFダウンロード
            receipts = []
            if items:
                try:
                    job_ref.update({"status": "downloading_receipts"})
                    receipts = await session.download_receipts(items)
                    print(f"[WS] Downloaded {len(receipts)} receipt PDFs")
                except Exception as e:
                    print(f"[WS] Receipt download error: {e}")

            # Drive にアップロード（PDF + CSV積み上げ）
            uploaded_files = []
            if items:
                try:
                    user_doc = db.collection("users").document(uid).get()
                    user_data = user_doc.to_dict() or {}
                    root_folder_id = user_data.get("driveRootFolderId", "")

                    if root_folder_id:
                        drive_tokens = get_drive_tokens(uid)
                        if drive_tokens and drive_tokens.get("driveRefreshToken"):
                            # ソース名を判定
                            source_name = {"amazon": "Amazon", "rakuten": "楽天", "yahoo": "Yahoo"}.get(site, "Amazon")

                            from drive_helper import upload_receipt_and_update_csv
                            uploaded_files = upload_receipt_and_update_csv(
                                items=items,
                                receipts=receipts,
                                root_folder_id=root_folder_id,
                                refresh_token=drive_tokens["driveRefreshToken"],
                                fiscal_year_start_month=user_data.get("fiscalYearStartMonth", 1),
                                source=source_name,
                            )
                            print(f"[WS] Uploaded {len(uploaded_files)} files to Drive")
                except Exception as e:
                    print(f"[WS] Drive upload error: {e}")
                    import traceback
                    traceback.print_exc()

            # Firestoreに結果保存
            job_ref.update({
                "status": "complete",
                "items": items,
                "uploadedFiles": uploaded_files,
            })
            print(f"[WS] Results saved to Firestore job {job_id}")

            # WebSocketがまだ生きていれば結果送信
            try:
                await websocket.send_json({
                    "type": "status",
                    "status": "complete",
                    "items": items,
                    "uploadedFiles": uploaded_files,
                    "jobId": job_id,
                })
                print("[WS] Results sent to client")
            except Exception:
                print("[WS] Client already disconnected, results saved in Firestore")

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        import traceback
        print(f"[WS] Fatal error: {e}")
        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        session._running = False
        if stream_task:
            stream_task.cancel()
            try:
                await stream_task
            except (asyncio.CancelledError, Exception):
                pass
        await session.close()
        print("[WS] Session closed")
