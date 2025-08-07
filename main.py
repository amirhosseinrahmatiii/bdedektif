import os
import io
import time
import random
import re
import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
import pyodbc

# Ortam değişkenleri
load_dotenv()

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")
SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DB = os.getenv("SQL_DB")
SQL_USER = os.getenv("SQL_USER")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")

app = FastAPI()

# Statik dosya (frontend) mount
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# Blob storage client
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
try:
    container_client.create_container()
except Exception:
    pass  # varsa hata verme

# OCR client
cv_client = ComputerVisionClient(AZURE_OCR_ENDPOINT, CognitiveServicesCredentials(AZURE_OCR_KEY))

# SQL connection
conn_str = f"Driver={{ODBC Driver 17 for SQL Server}};Server={SQL_SERVER};Database={SQL_DB};Uid={SQL_USER};Pwd={SQL_PASSWORD};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

# Tablo kontrolü
try:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INT IDENTITY(1,1) PRIMARY KEY,
        filename NVARCHAR(255),
        blob_url NVARCHAR(512),
        extracted_text NVARCHAR(MAX),
        total FLOAT,
        vat FLOAT,
        vendor NVARCHAR(255),
        created_at DATETIME DEFAULT GETDATE()
    )
    """)
except Exception as e:
    print("DB table error:", e)

# --- OCR, içerik ayıklama, SQL ve Blob işlemleri ---
def parse_invoice_text(text):
    # KDV, toplam, firma adını regex ile çek!
    total = 0
    vat = 0
    vendor = ""
    lines = text.splitlines()
    for line in lines:
        if not vendor and len(line.strip()) > 3 and not any(x in line for x in ["KDV", "TOPLAM", "FATURA", "TUTAR", "TL"]):
            vendor = line.strip()
        if "KDV" in line.upper():
            nums = re.findall(r"\d+[.,]?\d*", line)
            if nums:
                vat = float(nums[-1].replace(",", "."))
        if "TOPLAM" in line.upper() or "GENEL TOPLAM" in line.upper():
            nums = re.findall(r"\d+[.,]?\d*", line)
            if nums:
                total = float(nums[-1].replace(",", "."))
    return total, vat, vendor

@app.post("/upload-analyze")
async def upload_analyze(file: UploadFile = File(...)):
    # Dosya upload, blob'a yükle, OCR yap, parse et, SQL'e yaz
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Dosya boş")
    blob_name = f"{int(time.time())}_{random.randint(1000,9999)}_{file.filename}"
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(file_bytes, overwrite=True)
    blob_url = blob_client.url

    # OCR ile text çıkar (image ve pdf için!)
    extracted_text = ""
    if file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".pdf")):
        read_response = cv_client.read_in_stream(io.BytesIO(file_bytes), raw=True)
        operation_location = read_response.headers["Operation-Location"]
        operation_id = operation_location.split("/")[-1]
        for _ in range(10):
            result = cv_client.get_read_result(operation_id)
            if result.status.lower() not in ["notstarted", "running"]:
                break
            time.sleep(1)
        if result.status.lower() == "succeeded":
            for page in result.analyze_result.read_results:
                for line in page.lines:
                    extracted_text += line.text + "\n"
    elif file.filename.lower().endswith(".txt"):
        extracted_text = file_bytes.decode(errors="ignore")
    elif file.filename.lower().endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        extracted_text = "\n".join([p.text for p in doc.paragraphs])
    else:
        extracted_text = "Bu dosya formatı desteklenmiyor."

    total, vat, vendor = parse_invoice_text(extracted_text)
    cursor.execute(
        "INSERT INTO invoices (filename, blob_url, extracted_text, total, vat, vendor) VALUES (?, ?, ?, ?, ?, ?)",
        file.filename, blob_url, extracted_text, total, vat, vendor
    )

    return {
        "filename": file.filename,
        "blob_url": blob_url,
        "total": total,
        "vat": vat,
        "vendor": vendor,
        "extracted_text": extracted_text[:250]  # Özet
    }

@app.get("/records")
def get_records():
    cursor.execute("SELECT TOP 20 filename, total, vat, vendor, created_at, id FROM invoices ORDER BY created_at DESC")
    results = []
    for row in cursor.fetchall():
        results.append({
            "filename": row[0],
            "total": row[1],
            "vat": row[2],
            "vendor": row[3],
            "date": row[4].strftime("%Y-%m-%d %H:%M"),
            "id": row[5]
        })
    return {"records": results}

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))
