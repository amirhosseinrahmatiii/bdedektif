import os
import uuid
import datetime
import logging
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures

import pyodbc
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# .env (lokal geliştirme) yükle
# ---------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
log = logging.getLogger("belgededektif")

# ---------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------
app = FastAPI(
    title="BelgeDedektif API",
    description="Belgeleri yapay zeka ile analiz edip yöneten API.",
    version="1.0.0"
)

# Statik içerik (index.html, css, js)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------
# Sağlık kontrolü (App Service health check bununla bakıyor)
# ---------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------
# Kök sayfa (UI)
# ---------------------------------------------------------------------
@app.get("/", response_class=FileResponse)
async def serve_frontend():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------
# Azure istemcileri
# ---------------------------------------------------------------------
def get_azure_clients():
    """
    Blob ve Vision istemcilerini ortam değişkenlerinden üretir.
    Gerekli env:
      - AZURE_STORAGE_CONNECTION_STRING
      - AZURE_CONTAINER_NAME
      - AZURE_OCR_ENDPOINT
      - AZURE_OCR_KEY
    """
    try:
        connect_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        container_name = os.environ["AZURE_CONTAINER_NAME"]
        vision_endpoint = os.environ["AZURE_OCR_ENDPOINT"]
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


# ---------------------------------------------------------------------
# DB Bağlantısı
# ---------------------------------------------------------------------
def get_db_connection():
    """
    Azure SQL'e bağlanır. Gerekli env:
      - SQL_SERVER (bdedeksqlxxxx.database.windows.net)
      - SQL_DB
      - SQL_USER
      - SQL_PASSWORD
    """
    try:
        # Azure SQL yeni sürümlerde Encrypt zorunlu. Sertifika başarısız ise
        # TrustServerCertificate=yes eklenebilir (güvenlik açısından prod için önerilmez).
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={os.environ['SQL_SERVER']};"
            f"DATABASE={os.environ['SQL_DB']};"
            f"UID={os.environ['SQL_USER']};"
            f"PWD={os.environ['SQL_PASSWORD']};"
            f"Encrypt=yes;TrustServerCertificate=yes"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        log.exception("Veritabanı bağlantı hatası")
        raise HTTPException(status_code=500, detail=f"Veritabanı bağlantı hatası: {e}")


# ---------------------------------------------------------------------
# OCR helper (SDK sürüm farklarına dayanıklı)
# ---------------------------------------------------------------------
def run_ocr(vision_client: ImageAnalysisClient, blob_url: str, image_bytes: bytes):
    """
    azure-ai-vision-imageanalysis paketinin farklı minör sürümlerinde
    'analyze' imzası değişebiliyor. Önce image_data (bayt) ile dener,
    olmazsa URL ile fallback yapar.
    """
    # 1) image_data ile (named)
    try:
        return vision_client.analyze(
            image_data=image_bytes,
            visual_features=[VisualFeatures.READ]
        )
    except TypeError:
        pass

    # 2) image_data ile (positional)
    try:
        return vision_client.analyze(
            image_bytes,
            visual_features=[VisualFeatures.READ]
        )
    except Exception:
        # 3) En eski sürümler için URL ile
        return vision_client.analyze_from_url(
            image_url=blob_url,
            visual_features=[VisualFeatures.READ]
        )


def extract_text_from_result(result) -> str:
    try:
        if getattr(result, "read", None) and result.read.blocks:
            lines: List[str] = []
            for block in result.read.blocks:
                for line in block.lines:
                    lines.append(line.text)
            return "\n".join(lines) if lines else "Bu belgede okunabilir metin bulunamadı."
        return "Bu belgede okunabilir metin bulunamadı."
    except Exception:
        log.exception("OCR sonucundan metin çıkarılırken hata")
        return "Bu belgede okunabilir metin bulunamadı."


# ---------------------------------------------------------------------
# Yükle + Analiz
# ---------------------------------------------------------------------
@app.post("/api/upload-and-analyze")
async def upload_and_analyze_document(file: UploadFile = File(...)):
    """
    1) Dosyayı Blob'a yükle
    2) Vision ile OCR
    3) Sonucu DB'ye kaydet
    """
    blob_service_client, container_name, vision_client = get_azure_clients()

    try:
        # --- 1) Blob'a yükle ---
        ext = os.path.splitext(file.filename)[1]
        blob_name = f"doc-{uuid.uuid4()}{ext}"
        blob_client = blob_service_client.get_blob_client(
            container=container_name, blob=blob_name
        )

        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Boş dosya yüklendi.")

        blob_client.upload_blob(contents, overwrite=True)
        blob_url = blob_client.url
        log.info("Blob yüklendi: %s", blob_url)

        # --- 2) OCR ---
        result = run_ocr(vision_client, blob_url, contents)
        ocr_text = extract_text_from_result(result)

        # --- 3) DB kaydı ---
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO dbo.Belgeler (Ad, Tarih, Firma, OCR, BlobURL) "
                "VALUES (?, ?, ?, ?, ?)",
                file.filename,
                datetime.date.today(),
                "Bilinmiyor",
                ocr_text,
                blob_url,
            )
            conn.commit()

        return {"message": "Belge başarıyla analiz edildi.", "text": ocr_text, "blob_url": blob_url}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("upload-and-analyze sırasında hata")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Belgeleri listele
# ---------------------------------------------------------------------
@app.get("/api/documents")
def get_documents():
    try:
        docs = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT Id, Ad, Tarih, Firma, OCR, BlobURL "
                "FROM dbo.Belgeler ORDER BY Tarih DESC"
            )
            rows = cursor.fetchall()
            columns = [c[0] for c in cursor.description]
            for row in rows:
                item = dict(zip(columns, row))
                if isinstance(item.get("Tarih"), (datetime.date, datetime.datetime)):
                    item["Tarih"] = item["Tarih"].isoformat()
                docs.append(item)
        return docs
    except Exception as e:
        log.exception("Belgeler alınırken hata")
        raise HTTPException(status_code=500, detail=f"Belgeler alınırken hata oluştu: {e}")


# ---------------------------------------------------------------------
# Lokal çalıştırma
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
