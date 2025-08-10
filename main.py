# --- imports ---
import os
import uuid
import datetime
import traceback
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures

import pyodbc
from dotenv import load_dotenv


# --- environment & logging ---
load_dotenv()  # local geliştirirken .env okur (App Service prod'da App Settings kullanılıyor)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("belgededektif")


# --- FastAPI app ---
app = FastAPI(
    title="BelgeDedektif API",
    description="Belgeleri yapay zeka ile analiz edip yöneten API.",
    version="1.0.0"
)

# static klasörü varsa mount et (Azure'da klasör eksikse start-up patlamasın)
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# --- health check (App Service healthCheckPath = /api/health) ---
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0"
    }


# --- root (frontend) ---
@app.get("/", response_class=FileResponse)
async def serve_frontend():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    # index yoksa basit bir mesaj dönelim
    return JSONResponse({"message": "UI bulunamadı. /api/upload-and-analyze ve /api/documents endpointlerini kullanın."})


# --- Azure clients ---
def get_azure_clients():
    """
    Azure Blob + Image Analysis istemcilerini App Settings / .env'den oluşturur.
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
        logger.exception("Eksik ortam değişkeni: %s", e)
        raise HTTPException(status_code=500, detail=f"Sunucu yapılandırma hatası: {e} ortam değişkeni eksik.")


# --- DB connection ---
def get_db_connection():
    """
    Azure SQL'e pyodbc ile bağlanır.
    ODBC sürücüsü override etmek isterseniz ODBC_DRIVER=ODBC Driver 18 for SQL Server gibi set edebilirsiniz.
    """
    try:
        driver = os.getenv("ODBC_DRIVER", "ODBC Driver 17 for SQL Server")
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={os.environ['SQL_SERVER']};"
            f"DATABASE={os.environ['SQL_DB']};"
            f"UID={os.environ['SQL_USER']};"
            f"PWD={os.environ['SQL_PASSWORD']}"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        logger.exception("Veritabanı bağlantı hatası")
        # DEBUG modunda traceback ver (prod'da vermeyelim)
        if os.getenv("DEBUG", "false").lower() == "true":
            raise HTTPException(status_code=500, detail=f"Veritabanı bağlantı hatası: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Veritabanı bağlantı hatası: {e}")


# --- upload & analyze ---
@app.post("/api/upload-and-analyze")
async def upload_and_analyze_document(file: UploadFile = File(...)):
    """
    1) Dosyayı Blob'a yükler
    2) Azure Image Analysis 4.0 READ ile OCR yapar
    3) Sonucu Azure SQL'e kaydeder
    """
    blob_service_client, container_name, vision_client = get_azure_clients()

    try:
        # 1) Blob'a yükle
        ext = os.path.splitext(file.filename)[1] or ""
        blob_name = f"doc-{uuid.uuid4()}{ext}"
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

        contents = await file.read()
        blob_client.upload_blob(contents, overwrite=True)
        blob_url = blob_client.url
        logger.info("Blob'a yüklendi: %s", blob_url)

        # 2) OCR (Image Analysis v4)
        # SDK 1.0.0'da analyze(image_url=..., visual_features=[VisualFeatures.READ]) kullanılır.
        try:
            result = vision_client.analyze(
                image_url=blob_url,
                visual_features=[VisualFeatures.READ]
            )
        except HttpResponseError as http_err:
            logger.exception("Vision analyze çağrısı hata verdi")
            if os.getenv("DEBUG", "false").lower() == "true":
                raise HTTPException(status_code=502, detail=f"Vision API hatası: {http_err}\n{traceback.format_exc()}")
            raise HTTPException(status_code=502, detail=f"Vision API hatası: {http_err}")

        if getattr(result, "read", None) and result.read.blocks:
            lines = []
            for block in result.read.blocks:
                for line in block.lines:
                    lines.append(line.text)
            ocr_text = "\n".join(lines)
        else:
            ocr_text = "Bu belgede okunabilir metin bulunamadı."

        # 3) DB kaydı
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO dbo.Belgeler (Ad, Tarih, Firma, OCR, BlobURL) VALUES (?, ?, ?, ?, ?)",
                file.filename,
                datetime.date.today(),
                "Bilinmiyor",
                ocr_text,
                blob_url
            )
            conn.commit()

        return {"message": "Belge başarıyla analiz edildi.", "text": ocr_text, "blobUrl": blob_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload-and-analyze sırasında hata")
        if os.getenv("DEBUG", "false").lower() == "true":
            raise HTTPException(status_code=500, detail=f"Hata: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# --- list documents ---
@app.get("/api/documents")
def get_documents():
    """
    Kayıtlı belgeleri döner.
    """
    docs = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT Id, Ad, Tarih, Firma, OCR, BlobURL FROM dbo.Belgeler ORDER BY Tarih DESC")
            rows = cursor.fetchall()
            columns = [c[0] for c in cursor.description]
            for row in rows:
                item = dict(zip(columns, row))
                # Tarih'i ISO string yap
                if isinstance(item.get("Tarih"), (datetime.date, datetime.datetime)):
                    item["Tarih"] = item["Tarih"].isoformat()
                docs.append(item)
        return docs
    except Exception as e:
        logger.exception("/api/documents sırasında hata")
        if os.getenv("DEBUG", "false").lower() == "true":
            raise HTTPException(status_code=500, detail=f"Belgeler alınırken hata: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Belgeler alınırken hata: {e}")


# --- local debug run (Azure'da gerekmez) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
