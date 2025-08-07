from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import uuid
import pyodbc
from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials

# .env dosyasını yükle
load_dotenv()

# Ortam değişkenlerini oku
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")
SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DB = os.getenv("SQL_DB")
SQL_USER = os.getenv("SQL_USER")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")

app = FastAPI()

# CORS (Front-end ile API konuşsun diye)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static klasörü mount et
app.mount("/static", StaticFiles(directory="static"), name="static")

# SQL bağlantısı fonksiyonu
def get_sql_conn():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DB};"
        f"UID={SQL_USER};"
        f"PWD={SQL_PASSWORD}"
    )
    return pyodbc.connect(conn_str)

# Blob ve OCR clientları
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
computervision_client = ComputerVisionClient(AZURE_OCR_ENDPOINT, CognitiveServicesCredentials(AZURE_OCR_KEY))

@app.get("/", response_class=HTMLResponse)
def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/upload-analyze")
async def upload_analyze(file: UploadFile = File(...)):
    try:
        filename = f"{uuid.uuid4()}_{file.filename}"
        blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=filename)
        data = await file.read()
        blob_client.upload_blob(data, overwrite=True)
        blob_url = blob_client.url

        # OCR işle (sadece görsel/pdf için)
        ocr_text = ""
        if file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".pdf")):
            ocr_result = computervision_client.read(blob_url, raw=True)
            operation_location = ocr_result.headers["Operation-Location"]
            operation_id = operation_location.split("/")[-1]

            # OCR sonucu bekle (async, 10 saniye bekle)
            import time
            for _ in range(10):
                result = computervision_client.get_read_result(operation_id)
                if result.status in ["succeeded", "failed"]:
                    break
                time.sleep(1)
            if result.status == "succeeded":
                ocr_text = "\n".join([line.text for page in result.analyze_result.read_results for line in page.lines])

        # Dummy KDV/toplam vs. (analiz eklenecekse burası özelleştirilebilir)
        firma, kdv, toplam, tarih = "Algılanamadı", "Algılanamadı", "Algılanamadı", "Algılanamadı"
        # (OCR içinden veri ayıklama kodu burada olabilir)
        # Örneğin: if "KDV" in ocr_text: ... gibi

        # SQL'e kaydet
        conn = get_sql_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Belgeler (Ad, Tarih, Firma, KDV, Toplam, OCR, BlobURL)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            file.filename, tarih, firma, kdv, toplam, ocr_text, blob_url
        )
        conn.commit()
        conn.close()

        return {"success": True, "filename": file.filename, "ocr": ocr_text, "blob_url": blob_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/records")
def records():
    conn = get_sql_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT Ad, Tarih, Firma, KDV, Toplam, OCR, BlobURL FROM Belgeler ORDER BY id DESC")
    rows = cursor.fetchall()
    result = []
    for row in rows:
        result.append({
            "Ad": row[0],
            "Tarih": row[1],
            "Firma": row[2],
            "KDV": row[3],
            "Toplam": row[4],
            "OCR": row[5],
            "BlobURL": row[6]
        })
    conn.close()
    return {"records": result}
