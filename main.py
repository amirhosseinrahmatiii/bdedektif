# --- en üst kısımda importlar ---
import os
import datetime
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
import pyodbc
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="BelgeDedektif API", description="Belgeleri yapay zeka ile analiz edip yöneten API.", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Sağlık kontrolü (Azure Health Check path) ---
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

# --- Kök sayfa ---
@app.get("/", response_class=FileResponse)
async def serve_frontend():
    return FileResponse("static/index.html")  # <— string döndürme yerine dosyayı döndür

def get_azure_clients():
    try:
        connect_str = os.environ['AZURE_STORAGE_CONNECTION_STRING']
        container_name = os.environ['AZURE_CONTAINER_NAME']
        vision_endpoint = os.environ['AZURE_OCR_ENDPOINT']
        vision_key = os.environ['AZURE_OCR_KEY']

        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        vision_client = ImageAnalysisClient(endpoint=vision_endpoint, credential=AzureKeyCredential(vision_key))
        return blob_service_client, container_name, vision_client
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Sunucu yapılandırma hatası: {e} ortam değişkeni eksik.")

def get_db_connection():
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={os.environ['SQL_SERVER']};"
            f"DATABASE={os.environ['SQL_DB']};"
            f"UID={os.environ['SQL_USER']};"
            f"PWD={os.environ['SQL_PASSWORD']}"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Veritabanı bağlantı hatası: {e}")

@app.post("/api/upload-and-analyze")
async def upload_and_analyze_document(file: UploadFile = File(...)):
    blob_service_client, container_name, vision_client = get_azure_clients()
    try:
        # 1) Blob'a yükle
        ext = os.path.splitext(file.filename)[1]
        blob_name = f"doc-{uuid.uuid4()}{ext}"
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        contents = await file.read()
        blob_client.upload_blob(contents, overwrite=True)
        blob_url = blob_client.url

        # 2) Vision 4.0 ile OCR
        # Not: SDK sürümünde 'analyze' kullanılıyor ve URL'i keyword olarak vermek şart.
        result = vision_client.analyze(
            image_url=blob_url,
            visual_features=[VisualFeatures.READ]
        )

        ocr_text = (
            "\n".join([line.text for block in result.read.blocks for line in block.lines])
            if getattr(result, "read", None) and result.read.blocks else
            "Bu belgede okunabilir metin bulunamadı."
        )

        # 3) DB kaydı
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO dbo.Belgeler (Ad, Tarih, Firma, OCR, BlobURL) VALUES (?, ?, ?, ?, ?)",
                file.filename, datetime.date.today(), "Bilinmiyor", ocr_text, blob_url
            )
            conn.commit()

        return {"message": "Belge başarıyla analiz edildi.", "text": ocr_text}

    except Exception as e:
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
                # Tarih’i front-end için ISO string’e çevir
                if isinstance(item.get("Tarih"), (datetime.date, datetime.datetime)):
                    item["Tarih"] = item["Tarih"].isoformat()
                docs.append(item)
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Belgeler alınırken hata oluştu: {str(e)}")
