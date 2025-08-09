import os
import datetime
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
import pyodbc

# --- Uygulama Başlangıcı ve Yapılandırma ---
app = FastAPI(
    title="BelgeDedektif API",
    description="Belgeleri yapay zeka ile analiz edip yöneten API.",
    version="1.0.0"
)

# Static dosyaları (index.html, css, js) sunmak için
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Azure Servis Bağlantıları ---

# 1. Blob Storage İstemcisi
try:
    connect_str = os.environ['AZURE_STORAGE_CONNECTION_STRING']
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    container_name = os.environ['AZURE_CONTAINER_NAME']
except KeyError as e:
    print(f"HATA: Gerekli ortam değişkeni bulunamadı: {e}")
    blob_service_client = None
    container_name = None

# 2. Azure AI Vision (OCR) İstemcisi
try:
    vision_endpoint = os.environ['AZURE_OCR_ENDPOINT']
    vision_key = os.environ['AZURE_OCR_KEY']
    vision_client = ImageAnalysisClient(endpoint=vision_endpoint, credential=AzureKeyCredential(vision_key))
except KeyError as e:
    print(f"HATA: Gerekli AI Vision ortam değişkeni bulunamadı: {e}")
    vision_client = None

# 3. SQL Veritabanı Bağlantısı
def get_db_connection():
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={os.environ['SQL_SERVER']};"
            f"DATABASE={os.environ['SQL_DB']};"
            f"UID={os.environ['SQL_USER']};"
            f"PWD={os.environ['SQL_PASSWORD']}"
        )
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"Veritabanı bağlantı hatası: {e}")
        raise HTTPException(status_code=500, detail="Veritabanı bağlantısı kurulamadı.")

# --- API Endpoint'leri ---

@app.get("/", response_class=FileResponse)
async def read_index():
    """Uygulamanın ana HTML sayfasını sunar."""
    return "static/index.html"

@app.post("/upload-and-analyze")
async def upload_and_analyze_document(file: UploadFile = File(...)):
    """
    Belgeyi alır, Blob Storage'a yükler, AI ile analiz eder,
    sonuçları veritabanına kaydeder ve okunan metni döndürür.
    """
    if not all([blob_service_client, vision_client, container_name]):
        raise HTTPException(status_code=500, detail="Azure servis yapılandırması eksik.")

    try:
        # 1. Dosyayı Blob Storage'a Yükle
        file_extension = os.path.splitext(file.filename)[1]
        blob_name = f"doc-{uuid.uuid4()}{file_extension}"
        
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        contents = await file.read()
        blob_client.upload_blob(contents, overwrite=True)
        blob_url = blob_client.url

        # 2. AI Vision ile Metinleri Oku (OCR)
        result = vision_client.analyze(image_url=blob_url, visual_features=[VisualFeatures.READ])
        
        ocr_text = ""
        if result.read is not None and result.read.blocks:
            ocr_text = "\n".join([line.text for block in result.read.blocks for line in block.lines])

        # 3. Sonuçları Veritabanına Kaydet
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.Belgeler (Ad, Tarih, Firma, OCR, BlobURL) VALUES (?, ?, ?, ?, ?)",
            file.filename,
            datetime.date.today(),
            "Bilinmiyor", # Bu alan daha sonra AI ile doldurulabilir
            ocr_text,
            blob_url
        )
        conn.commit()
        cursor.close()
        conn.close()

        return {"message": "Belge başarıyla analiz edildi.", "text": ocr_text, "blob_url": blob_url}

    except Exception as e:
        print(f"İşlem sırasında hata: {e}")
        raise HTTPException(status_code=500, detail=f"İşlem sırasında bir hata oluştu: {str(e)}")

@app.get("/health")
def health_check():
    """Servislerin sağlık durumunu kontrol eder."""
    try:
        # Veritabanı bağlantısını test et
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "database_connection": "successful"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "database_connection": f"failed: {str(e)}"})
