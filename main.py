import os
import json
import uuid
import datetime
import logging
import imghdr
import time
import inspect
from typing import List, Optional
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.credentials import AzureKeyCredential
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
import pyodbc
import requests
from dotenv import load_dotenv

# Pillow for image processing
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
log = logging.getLogger("belgededektif")

# FastAPI app
app = FastAPI(
    title="BelgeDedektif API",
    description="Belgeleri yapay zeka ile analiz edip yöneten gelişmiş API.",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production'da kısıtla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Constants
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_IMAGE_DIMENSION = 4000
SUPPORTED_IMAGE_TYPES = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
SUPPORTED_DOC_TYPES = {'.pdf', '.docx', '.txt'}


def is_valid_image_bytes(data: bytes) -> bool:
    """Dosyanın gerçek bir görüntü olup olmadığını kontrol eder."""
    if len(data) < 16:
        return False

    # Magic bytes kontrolü
    magic_signatures = [
        (b"\xFF\xD8\xFF", "jpeg"),
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"GIF87a", "gif"),
        (b"GIF89a", "gif"),
        (b"BM", "bmp"),
        (b"RIFF", "webp"),
    ]

    head = data[:16]
    for sig, _ in magic_signatures:
        if head.startswith(sig):
            return True

    # imghdr ile ikinci kontrol
    try:
        kind = imghdr.what(None, h=data[:1024])
        if kind:
            return True
    except Exception:
        pass

    # Pillow ile son kontrol
    if PILLOW_AVAILABLE:
        try:
            Image.open(BytesIO(data)).verify()
            return True
        except Exception:
            pass

    return False


def normalize_image_bytes(data: bytes) -> bytes:
    """Görüntüyü optimize eder ve boyutunu düzenler."""
    if not PILLOW_AVAILABLE:
        return data

    try:
        with Image.open(BytesIO(data)) as img:
            # EXIF rotation düzeltmesi
            if hasattr(img, '_getexif'):
                exif = img._getexif()
                if exif is not None:
                    orientation = exif.get(274)  # Orientation tag
                    if orientation == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation == 6:
                        img = img.rotate(270, expand=True)
                    elif orientation == 8:
                        img = img.rotate(90, expand=True)

            # Boyut kontrolü ve küçültme
            if max(img.size) > MAX_IMAGE_DIMENSION:
                img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                log.info(f"Image resized to {img.size}")

            # Format optimizasyonu
            output = BytesIO()
            if img.mode in ('RGBA', 'LA', 'P'):
                # PNG olarak kaydet (transparency korunur)
                img.save(output, format='PNG', optimize=True)
            else:
                # RGB'ye çevir ve JPEG olarak kaydet
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(output, format='JPEG', quality=92, optimize=True)

            return output.getvalue()
    except Exception as e:
        log.warning(f"Image normalization failed: {e}")
        return data


def get_azure_clients():
    """Azure istemcilerini döndürür."""
    try:
        connect_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        container_name = os.environ.get("AZURE_CONTAINER_NAME", "belgededektif")
        vision_endpoint = os.environ["AZURE_OCR_ENDPOINT"].rstrip("/")
        vision_key = os.environ["AZURE_OCR_KEY"]

        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        vision_client = ImageAnalysisClient(
            endpoint=vision_endpoint,
            credential=AzureKeyCredential(vision_key)
        )

        return blob_service_client, container_name, vision_client
    except KeyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Sunucu yapılandırma hatası: {e} ortam değişkeni eksik."
        )


def get_db_connection():
    """Veritabanı bağlantısını döndürür."""
    try:
        conn_str = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={os.environ['SQL_SERVER']};"
            f"DATABASE={os.environ['SQL_DB']};"
            f"UID={os.environ['SQL_USER']};"
            f"PWD={os.environ['SQL_PASSWORD']};"
            "Encrypt=yes;TrustServerCertificate=yes"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        log.exception("Veritabanı bağlantı hatası")
        raise HTTPException(
            status_code=500,
            detail=f"Veritabanı bağlantı hatası: {str(e)}"
        )


def vision_read_bytes(image_bytes: bytes, timeout_sec: int = 30) -> str:
    """Azure Vision Read API ile OCR yapar."""
    try:
        endpoint = os.environ["AZURE_OCR_ENDPOINT"].rstrip("/")
        key = os.environ["AZURE_OCR_KEY"]

        # 1. Analyze isteği
        url = f"{endpoint}/vision/v3.2/read/analyze"
        headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/octet-stream"
        }

        response = requests.post(url, headers=headers, data=image_bytes, timeout=20)
        response.raise_for_status()

        operation_location = response.headers.get("Operation-Location")
        if not operation_location:
            raise RuntimeError("Operation-Location header missing")

        # 2. Polling
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            time.sleep(1.5)

            poll_response = requests.get(
                operation_location,
                headers={"Ocp-Apim-Subscription-Key": key},
                timeout=20
            )
            poll_response.raise_for_status()

            result = poll_response.json()
            status = result.get("status")

            if status == "succeeded":
                lines = []
                for read_result in result.get("analyzeResult", {}).get("readResults", []):
                    for line in read_result.get("lines", []):
                        text = line.get("text")
                        if text:
                            lines.append(text)

                return "\n".join(lines).strip() if lines else "Bu belgede okunabilir metin bulunamadı."

            elif status == "failed":
                error_msg = result.get("message", "OCR işlemi başarısız")
                raise RuntimeError(f"Vision Read failed: {error_msg}")

        raise TimeoutError("OCR işlemi zaman aşımına uğradı")

    except requests.exceptions.RequestException as e:
        log.exception("Vision API request error")
        raise HTTPException(status_code=500, detail=f"OCR servisi hatası: {str(e)}")
    except Exception as e:
        log.exception("Vision Read error")
        raise HTTPException(status_code=500, detail=f"OCR hatası: {str(e)}")


def save_to_blob(filename: str, data: bytes, mime_type: str) -> str:
    """Dosyayı Azure Blob Storage'a kaydeder."""
    try:
        blob_service_client, container_name, _ = get_azure_clients()

        # Dosya adı ve yol oluştur
        today = datetime.datetime.utcnow()
        file_id = str(uuid.uuid4())

        # Güvenli dosya adı oluştur
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ".-_").strip()
        if not safe_filename:
            safe_filename = "upload"

        # Blob yolu
        blob_path = f"belgededektif/{today:%Y/%m/%d}/{file_id}-{safe_filename}"

        # Blob client
        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_path
        )

        # Content settings
        content_settings = ContentSettings(
            content_type=mime_type,
            content_disposition=f'inline; filename="{safe_filename}"'
        )

        # Upload
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=content_settings
        )

        return blob_client.url

    except Exception as e:
        log.exception("Blob upload error")
        raise HTTPException(status_code=500, detail=f"Dosya yükleme hatası: {str(e)}")


def create_document_record(filename: str, size: int, mime_type: str, blob_url: str, status: str = "processing") -> str:
    """Veritabanında belge kaydı oluşturur."""
    try:
        doc_id = str(uuid.uuid4())
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dbo.Belgeler (Id, Ad, Tarih, Firma, OCR, BlobURL, Status, Size, MimeType)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, doc_id, filename, datetime.date.today(), "Bilinmiyor", "", blob_url, status, size, mime_type)
            conn.commit()
        return doc_id
    except Exception as e:
        log.exception("Database insert error")
        raise HTTPException(status_code=500, detail=f"Veritabanı kayıt hatası: {str(e)}")


def update_document_record(doc_id: str, status: str, ocr_text: str = ""):
    """Belge kaydını günceller."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE dbo.Belgeler 
                SET Status = ?, OCR = ?, UpdatedAt = ?
                WHERE Id = ?
            """, status, ocr_text, datetime.datetime.utcnow(), doc_id)
            conn.commit()
    except Exception as e:
        log.exception("Database update error")
        raise HTTPException(status_code=500, detail=f"Veritabanı güncelleme hatası: {str(e)}")


@app.get("/api/diag")
def diagnostics():
    """Diagnostics: Env değişkenlerini ve analyze fonksiyon imzasını gösterir."""
    env_keys = [
        "AZURE_OCR_ENDPOINT", "AZURE_OCR_KEY", "AZURE_STORAGE_CONNECTION_STRING",
        "SQL_SERVER", "SQL_DB", "SQL_USER", "SQL_PASSWORD", "AZURE_CONTAINER_NAME"
    ]
    env_present = {key: bool(os.getenv(key)) for key in env_keys}

    # Analyze fonksiyonunun imzası (çağırmadan, sadece imza metni)
    try:
        analyze_signature = str(inspect.signature(ImageAnalysisClient.analyze))
    except Exception as e:
        analyze_signature = f"İmza okunamadı: {e}"

    return {
        "env_present": env_present,
        "analyze_signature": analyze_signature
    }


@app.get("/")
async def serve_frontend(request: Request):
    """Ana sayfa."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
def health():
    """Sağlık kontrolü."""
    return {
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }


@app.post("/api/upload-and-analyze")
async def upload_and_analyze_document(file: UploadFile = File(...)):
    """Belge yükleme ve analiz."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Boş dosya yüklendi.")

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Dosya çok büyük. Maksimum {MAX_FILE_SIZE // (1024*1024)}MB olmalı."
        )

    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in SUPPORTED_IMAGE_TYPES and file_ext not in SUPPORTED_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen dosya türü: {file_ext}"
        )

    if file_ext in SUPPORTED_IMAGE_TYPES:
        if not is_valid_image_bytes(contents):
            raise HTTPException(
                status_code=400,
                detail="Geçersiz görüntü formatı. Lütfen gerçek bir PNG/JPEG/GIF yükleyin."
            )
        contents = normalize_image_bytes(contents)

    try:
        blob_url = save_to_blob(
            file.filename or "upload",
            contents,
            file.content_type or "application/octet-stream"
        )

        doc_id = create_document_record(
            file.filename or "upload",
            len(contents),
            file.content_type or "application/octet-stream",
            blob_url,
            "processing"
        )

        try:
            if file_ext in SUPPORTED_IMAGE_TYPES:
                ocr_text = vision_read_bytes(contents)
            else:
                ocr_text = "Bu dosya türü için OCR henüz desteklenmiyor."

            update_document_record(doc_id, "succeeded", ocr_text)

            return {
                "id": doc_id,
                "message": "Belge başarıyla analiz edildi.",
                "text": ocr_text,
                "blob_url": blob_url,
                "filename": file.filename,
                "size": len(contents)
            }

        except Exception as ocr_error:
            update_document_record(doc_id, "failed", str(ocr_error))
            raise HTTPException(
                status_code=500,
                detail=f"OCR işlemi başarısız: {str(ocr_error)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Upload and analyze error")
        raise HTTPException(status_code=500, detail=f"İşlem hatası: {str(e)}")


@app.get("/api/documents")
def get_documents():
    """Belgeleri listeler."""
    try:
        docs = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, Ad, Tarih, Firma, OCR, BlobURL, Status, Size, MimeType, UpdatedAt
                FROM dbo.Belgeler 
                ORDER BY Tarih DESC
            """)

            columns = [col[0] for col in cursor.description]
            for row in cursor.fetchall():
                doc = dict(zip(columns, row))

                for date_field in ['Tarih', 'UpdatedAt']:
                    if doc.get(date_field) and isinstance(doc[date_field], (datetime.date, datetime.datetime)):
                        doc[date_field] = doc[date_field].isoformat()

                docs.append(doc)

        return {"documents": docs, "count": len(docs)}

    except Exception as e:
        log.exception("Get documents error")
        raise HTTPException(status_code=500, detail=f"Belgeler alınırken hata: {str(e)}")


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    """Tek belge detayı."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, Ad, Tarih, Firma, OCR, BlobURL, Status, Size, MimeType, UpdatedAt
                FROM dbo.Belgeler 
                WHERE Id = ?
            """, doc_id)

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Belge bulunamadı")

            columns = [col[0] for col in cursor.description]
            doc = dict(zip(columns, row))

            for date_field in ['Tarih', 'UpdatedAt']:
                if doc.get(date_field) and isinstance(doc[date_field], (datetime.date, datetime.datetime)):
                    doc[date_field] = doc[date_field].isoformat()

            return doc

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Get document error")
        raise HTTPException(status_code=500, detail=f"Belge alınırken hata: {str(e)}")


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    """Belge siler."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dbo.Belgeler WHERE Id = ?", doc_id)

            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Belge bulunamadı")

            conn.commit()

        return {"message": "Belge başarıyla silindi"}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Delete document error")
        raise HTTPException(status_code=500, detail=f"Belge silinirken hata: {str(e)}")


# İstatistik endpoint'i (ana bloktan önce)
@app.get("/api/stats")
def get_stats():
    """Belgeler hakkında istatistik döndürür."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM dbo.Belgeler")
            total_docs = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM dbo.Belgeler WHERE Status='succeeded'")
            success_count = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(Tarih) FROM dbo.Belgeler")
            last_upload = cursor.fetchone()[0]
            if isinstance(last_upload, (datetime.date, datetime.datetime)):
                last_upload = last_upload.isoformat()

        return {
            "total_documents": total_docs,
            "success_count": success_count,
            "success_rate": f"{(success_count/total_docs*100):.2f}%" if total_docs else "0%",
            "last_upload": last_upload
        }

    except Exception as e:
        log.exception("Stats error")
        raise HTTPException(status_code=500, detail=f"İstatistik alınırken hata: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


doğrumu
