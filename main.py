# main.py — BelgeDedektif API (stabil)
import os
import sys
import datetime
import uuid
import logging
import inspect
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures

import pyodbc
from dotenv import load_dotenv

# -------------------------------------------------
# Boot
# -------------------------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="BelgeDedektif API",
    description="Belgeleri yapay zeka ile analiz edip yöneten API.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Static mount: klasör yoksa mount etme (App Service crash'ini önler)
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------------------------------------
# Health / Root
# -------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

@app.get("/", response_class=FileResponse)
async def serve_frontend():
    # static/index.html varsa bunu döndürür; yoksa 404 olur (app crash etmez)
    return FileResponse("static/index.html")


# -------------------------------------------------
# Azure Clients
# -------------------------------------------------
def _get_vision_cfg():
    # Birden fazla isimlendirmeyi destekle
    endpoint = (
        os.getenv("AZURE_OCR_ENDPOINT")
        or os.getenv("VISION_ENDPOINT")
        or os.getenv("COGNITIVE_ENDPOINT")
        or ""
    ).rstrip("/")
    key = (
        os.getenv("AZURE_OCR_KEY")
        or os.getenv("VISION_KEY")
        or os.getenv("COGNITIVE_KEY")
        or ""
    )
    if not endpoint or not key:
        raise KeyError("AZURE_OCR_ENDPOINT/AZURE_OCR_KEY (veya VISION_ENDPOINT/VISION_KEY) eksik")
    return endpoint, key


def get_azure_clients():
    try:
        connect_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        container_name = os.environ.get("AZURE_CONTAINER_NAME") or "belgededektif"
        vision_endpoint, vision_key = _get_vision_cfg()

        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        vision_client = ImageAnalysisClient(
            endpoint=vision_endpoint,
            credential=AzureKeyCredential(vision_key),
        )
        return blob_service_client, container_name, vision_client
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Sunucu yapılandırma hatası: {e} ortam değişkeni eksik.")


def get_db_connection():
    server = os.environ.get("SQL_SERVER")
    db = os.environ.get("SQL_DB")
    user = os.environ.get("SQL_USER")
    pwd = os.environ.get("SQL_PASSWORD")
    if not all([server, db, user, pwd]):
        raise HTTPException(status_code=500, detail="SQL bağlantı bilgileri eksik.")

    errors = []
    for driver in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        try:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};DATABASE={db};UID={user};PWD={pwd};"
                "Encrypt=yes;TrustServerCertificate=yes;"
            )
            return pyodbc.connect(conn_str)
        except Exception as e:
            errors.append(f"{driver}: {e}")
            continue
    raise HTTPException(status_code=500, detail="Veritabanı bağlantı hatası: " + " | ".join(errors))


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _is_supported_image(contents: bytes) -> bool:
    if not contents or len(contents) < 8:
        return False
    head = contents[:8]
    is_png = head.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpg = head.startswith(b"\xff\xd8\xff")
    return is_png or is_jpg


def _run_ocr(vision_client: ImageAnalysisClient, contents: bytes, blob_url: str):
    """
    Azure SDK sürümlerindeki imza farklarına dayanıklı çağrı.
    Sırasıyla farklı imzaları dener; çalışanı ilkinde döner.
    """
    attempts = [
        # Yeni SDK
        lambda: vision_client.analyze(image_data=contents, visual_features=[VisualFeatures.READ]),
        lambda: vision_client.analyze(image_url=blob_url, visual_features=[VisualFeatures.READ]),
        # Bazı imzalarda parametre adı 'features'
        lambda: vision_client.analyze(image_data=contents, features=[VisualFeatures.READ]),
        lambda: vision_client.analyze(image_url=blob_url, features=[VisualFeatures.READ]),
        # Pozisyonel argüman olarak ver
        lambda: vision_client.analyze(contents, visual_features=[VisualFeatures.READ]),
        lambda: vision_client.analyze(blob_url, visual_features=[VisualFeatures.READ]),
        # BytesIO ile ver
        lambda: vision_client.analyze(BytesIO(contents), visual_features=[VisualFeatures.READ]),
    ]
    last_err = None
    for call in attempts:
        try:
            return call()
        except (TypeError, ValueError, AttributeError) as e:
            last_err = e
            continue
        except Exception as e:
            # Kritik spesifik hata ise dışarı taşı
            last_err = e
            break
    raise RuntimeError(f"Vision analyze çağrıları başarısız: {last_err}")


def _extract_text_from_result(result) -> str:
    """
    imageanalysis result nesnesinden metni güvenli şekilde ayıkla.
    """
    try:
        read = getattr(result, "read", None)
        if read and getattr(read, "blocks", None):
            lines = []
            for block in read.blocks:
                for line in getattr(block, "lines", []) or []:
                    if getattr(line, "text", None):
                        lines.append(line.text)
            text = "\n".join(lines).strip()
            if text:
                return text
    except Exception:
        pass
    # Son çare: string temsili (gürültüyü azalt)
    return "Bu belgede okunabilir metin bulunamadı."


# -------------------------------------------------
# Endpoints
# -------------------------------------------------
@app.post("/api/upload-and-analyze")
async def upload_and_analyze_document(file: UploadFile = File(...)):
    blob_service_client, container_name, vision_client = get_azure_clients()

    try:
        # 1) Blob'a yükle
        ext = os.path.splitext(file.filename)[1] or ".bin"
        blob_name = f"doc-{uuid.uuid4()}{ext}"
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

        contents = await file.read()
        if not _is_supported_image(contents):
            raise HTTPException(status_code=415, detail="Sadece JPG/PNG desteklenir veya geçersiz görüntü.")

        blob_client.upload_blob(contents, overwrite=True)
        blob_url = blob_client.url

        # 2) OCR — imzaya göre esnek çağrı
        result = _run_ocr(vision_client, contents, blob_url)
        ocr_text = _extract_text_from_result(result)

        # 3) DB Kaydı (opsiyonel hata logla, kullanıcıya yansıtma)
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO dbo.Belgeler (Ad, Tarih, Firma, OCR, BlobURL) VALUES (?, ?, ?, ?, ?)",
                    file.filename, datetime.date.today(), "Bilinmiyor", ocr_text, blob_url
                )
                conn.commit()
        except Exception as db_err:
            logging.error(f"DB kaydı başarısız: {db_err}")

        return {"message": "Belge başarıyla analiz edildi.", "text": ocr_text, "blob_url": blob_url}

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("upload-and-analyze hata")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
def get_documents():
    docs = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT Id, Ad, Tarih, Firma, OCR, BlobURL FROM dbo.Belgeler ORDER BY Tarih DESC")
            rows = cursor.fetchall()
            columns = [c[0] for c in cursor.description]
            for row in rows:
                item = dict(zip(columns, row))
                if isinstance(item.get("Tarih"), (datetime.date, datetime.datetime)):
                    item["Tarih"] = item["Tarih"].isoformat()
                docs.append(item)
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Belgeler alınırken hata oluştu: {str(e)}")


# -------------------------------------------------
# Teşhis Endpoint
# -------------------------------------------------
@app.get("/api/diag")
def diag():
    # paket sürümleri
    def _ver(pkg):
        try:
            import importlib.metadata as md
            return md.version(pkg)
        except Exception:
            try:
                import pkg_resources as pr
                return pr.get_distribution(pkg).version
            except Exception:
                return None

    analyze_sig = None
    try:
        _, _, vc = get_azure_clients()
        analyze_sig = str(inspect.signature(vc.analyze))
    except Exception as e:
        analyze_sig = f"inspect failed: {e}"

    return {
        "time": datetime.datetime.utcnow().isoformat(),
        "python": sys.version,
        "packages": {
            "azure-ai-vision-imageanalysis": _ver("azure-ai-vision-imageanalysis"),
            "azure-storage-blob": _ver("azure-storage-blob"),
            "azure-core": _ver("azure-core"),
            "fastapi": _ver("fastapi"),
            "pyodbc": _ver("pyodbc"),
        },
        "env_present": {
            "AZURE_STORAGE_CONNECTION_STRING": bool(os.getenv("AZURE_STORAGE_CONNECTION_STRING")),
            "AZURE_OCR_ENDPOINT_or_VISION_ENDPOINT": bool(os.getenv("AZURE_OCR_ENDPOINT") or os.getenv("VISION_ENDPOINT")),
            "AZURE_OCR_KEY_or_VISION_KEY": bool(os.getenv("AZURE_OCR_KEY") or os.getenv("VISION_KEY")),
            "SQL_*": all(bool(os.getenv(k)) for k in ("SQL_SERVER", "SQL_DB", "SQL_USER", "SQL_PASSWORD")),
        },
        "static_exists": os.path.isdir("static"),
        "analyze_signature": analyze_sig,
    }
