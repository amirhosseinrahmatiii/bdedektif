import os
import io
import time
import random
import datetime
import re
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
import pyodbc
import openai

# .env'den tüm ayarları al
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DB = os.getenv("SQL_DB")
SQL_USER = os.getenv("SQL_USER")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")

# FastAPI app başlat
app = FastAPI()

# Statik dosya (arayüz) bağla
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

# Azure servislerini başlat
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
cv_client = ComputerVisionClient(AZURE_OCR_ENDPOINT, CognitiveServicesCredentials(AZURE_OCR_KEY))
openai.api_key = OPENAI_API_KEY

# SQL bağlantısı
conn_str = (
    "Driver={ODBC Driver 17 for SQL Server};"
    f"Server={SQL_SERVER};"
    f"Database={SQL_DB};"
    f"Uid={SQL_USER};"
    f"Pwd={SQL_PASSWORD};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

# Tablo oluştur (varsa atla)
try:
    cursor.execute("""
        CREATE TABLE invoices (
            id INT IDENTITY(1,1) PRIMARY KEY,
            file_name NVARCHAR(255),
            blob_url NVARCHAR(500),
            extracted_text NVARCHAR(MAX),
            total_amount DECIMAL(10,2),
            vat_amount DECIMAL(10,2),
            vendor_name NVARCHAR(255),
            uploaded_at DATETIME DEFAULT GETDATE()
        )
    """)
except Exception as e:
    if "There is already an object named" not in str(e):
        print("DB table error:", e)

# OCR ve basit analiz
def parse_invoice_text(text):
    total, vat, vendor = None, None, ""
    # Burada daha gelişmiş bir regex ve metin analiz kodu kullanılabilir
    lines = text.splitlines()
    for l in lines:
        if not vendor and not re.search(r'\d', l):
            vendor = l.strip()
        if not total and ("toplam" in l.lower() or "total" in l.lower()):
            num = re.findall(r"[\d.,]+", l)
            if num: total = float(num[-1].replace(",", "."))
        if not vat and ("kdv" in l.lower() or "vat" in l.lower()):
            num = re.findall(r"[\d.,]+", l)
            if num: vat = float(num[-1].replace(",", "."))
    return total or 0.0, vat or 0.0, vendor or ""

# Dosya yükle ve analiz et
@app.post("/upload-analyze")
async def upload_analyze(file: UploadFile = File(...)):
    # 1. Dosyayı Blob'a kaydet
    file_bytes = await file.read()
    unique_name = f"{int(time.time()*1000)}_{random.randint(1000,9999)}_{file.filename}"
    blob_client = container_client.get_blob_client(unique_name)
    blob_client.upload_blob(file_bytes, overwrite=True)
    blob_url = blob_client.url

    # 2. OCR ile metin çıkar
    ocr_text = ""
    try:
        read_response = cv_client.read_in_stream(io.BytesIO(file_bytes), raw=True)
        operation_id = read_response.headers["Operation-Location"].split("/")[-1]
        for _ in range(10):
            result = cv_client.get_read_result(operation_id)
            if result.status.lower() == "succeeded":
                ocr_text = "\n".join([line.text for page in result.analyze_result.read_results for line in page.lines])
                break
            time.sleep(1)
    except Exception as e:
        ocr_text = ""

    # 3. Temel analiz (KDV/toplam/vendor vs)
    total, vat, vendor = parse_invoice_text(ocr_text)

    # 4. SQL'e kaydet
    cursor.execute("""
        INSERT INTO invoices (file_name, blob_url, extracted_text, total_amount, vat_amount, vendor_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (file.filename, blob_url, ocr_text, total, vat, vendor))

    return {
        "message": "Başarılı!",
        "filename": file.filename,
        "blob_url": blob_url,
        "extracted_text": ocr_text[:200] + ("..." if len(ocr_text) > 200 else ""),
        "total_amount": total,
        "vat_amount": vat,
        "vendor_name": vendor
    }

# Kayıtları getir
@app.get("/records")
def records():
    cursor.execute("SELECT id, file_name, blob_url, total_amount, vat_amount, vendor_name, uploaded_at FROM invoices ORDER BY uploaded_at DESC")
    rows = cursor.fetchall()
    return {"records": [
        {
            "id": r[0], "filename": r[1], "blob_url": r[2],
            "total_amount": float(r[3] or 0), "vat_amount": float(r[4] or 0),
            "vendor_name": r[5], "uploaded_at": str(r[6])
        }
        for r in rows
    ]}

# Bir dosya hakkında OpenAI'ye soru sor
@app.post("/ask")
async def ask_ai(id: int = Form(...), question: str = Form(...)):
    cursor.execute("SELECT extracted_text FROM invoices WHERE id=?", id)
    row = cursor.fetchone()
    if not row or not row[0]:
        return {"answer": "Belge bulunamadı."}
    text = row[0]
    prompt = f"Belge içeriği:\n{text}\nKullanıcı sorusu: {question}\nKısa, açık, doğru cevap ver."
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Belge sorularını kısa, net ve doğru yanıtla."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,
        temperature=0.2
    )
    return {"answer": response["choices"][0]["message"]["content"].strip()}

