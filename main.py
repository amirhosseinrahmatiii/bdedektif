import os
import uuid
import pyodbc
import openai
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
from PyPDF2 import PdfReader
from docx import Document

# ENV yükle
load_dotenv()

# Config
blob_conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
blob_container = os.getenv("AZURE_CONTAINER_NAME")
ocr_endpoint = os.getenv("AZURE_OCR_ENDPOINT")
ocr_key = os.getenv("AZURE_OCR_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")
sql_server = os.getenv("SQL_SERVER")
sql_db = os.getenv("SQL_DB")
sql_user = os.getenv("SQL_USER")
sql_pass = os.getenv("SQL_PASSWORD")

# App başlat
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Static dosyalar
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def home():
    with open(os.path.join(static_dir, "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())

def get_sql_conn():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={sql_server};DATABASE={sql_db};UID={sql_user};PWD={sql_pass}"
    )
    return pyodbc.connect(conn_str)

def save_to_sql(filename, date, company, vat, total, text, blob_url):
    try:
        conn = get_sql_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Belgeler (Ad, Tarih, Firma, KDV, Toplam, OCR, BlobURL)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, filename, date, company, vat, total, text, blob_url)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("SQL ERROR:", e)

def upload_to_blob(file: UploadFile, content):
    blob_service = BlobServiceClient.from_connection_string(blob_conn_str)
    fname = str(uuid.uuid4()) + "_" + file.filename
    blob_client = blob_service.get_blob_client(container=blob_container, blob=fname)
    blob_client.upload_blob(content, overwrite=True)
    blob_url = blob_client.url
    return blob_url

def ocr_text(path, filetype):
    # Universal OCR
    if filetype in ["jpg", "jpeg", "png"]:
        client = ComputerVisionClient(ocr_endpoint, CognitiveServicesCredentials(ocr_key))
        with open(path, "rb") as image_stream:
            ocr_result = client.recognize_printed_text_in_stream(image=image_stream, language="tr")
        lines = []
        for r in ocr_result.regions:
            for l in r.lines:
                lines.append(" ".join([w.text for w in l.words]))
        return "\n".join(lines)
    elif filetype == "pdf":
        pdf = PdfReader(path)
        return "\n".join([p.extract_text() or "" for p in pdf.pages])
    elif filetype == "docx":
        doc = Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    elif filetype == "txt":
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""

def extract_info(text):
    # Demo: Basit regex ile KDV/toplam/tarih/firma (Geliştirilebilir!)
    import re
    tarih = re.findall(r"\d{2}[./-]\d{2}[./-]\d{4}", text)
    kdv = re.findall(r"KDV[^\d]*(\d+[\.,]?\d*)", text, re.IGNORECASE)
    toplam = re.findall(r"TOPLAM[^\d]*(\d+[\.,]?\d*)", text, re.IGNORECASE)
    firma = re.findall(r"(?:Ticaret|Ltd\.? Şti\.?|A\.Ş\.?|\.Şirketi|Firma)\s*([^\n]*)", text, re.IGNORECASE)
    return {
        "tarih": tarih[0] if tarih else "",
        "kdv": kdv[0] if kdv else "",
        "toplam": toplam[0] if toplam else "",
        "firma": firma[0] if firma else "",
    }

@app.post("/upload-analyze")
async def upload_analyze(file: UploadFile = File(...)):
    # 1. Blob'a yükle
    content = await file.read()
    blob_url = upload_to_blob(file, content)
    # 2. Geçici dosya kaydet
    tmp_path = "/tmp/" + file.filename
    with open(tmp_path, "wb") as f:
        f.write(content)
    ext = file.filename.split(".")[-1].lower()
    # 3. OCR veya içeriği oku
    text = ocr_text(tmp_path, ext)
    info = extract_info(text)
    # 4. SQL'e kaydet
    save_to_sql(file.filename, info["tarih"], info["firma"], info["kdv"], info["toplam"], text, blob_url)
    # 5. Sonucu döndür
    return {
        "filename": file.filename,
        "blob_url": blob_url,
        "tarih": info["tarih"],
        "firma": info["firma"],
        "kdv": info["kdv"],
        "toplam": info["toplam"],
        "ocr_text": text
    }

@app.get("/records")
def get_records():
    conn = get_sql_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT Ad, Tarih, Firma, KDV, Toplam, BlobURL FROM Belgeler ORDER BY id DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    data = [
        {"ad": r[0], "tarih": r[1], "firma": r[2], "kdv": r[3], "toplam": r[4], "blob_url": r[5]}
        for r in rows
    ]
    return {"records": data}

@app.post("/ai-ask")
async def ai_ask(filename: str = Form(...), question: str = Form(...)):
    conn = get_sql_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT OCR FROM Belgeler WHERE Ad=?", filename)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return {"answer": "Belge bulunamadı"}
    text = row[0][:8000]
    # AI ile soruyu yanıtla
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system", "content":"Aşağıda bir fatura/fiş OCR metni var. Soruya bu metne göre cevap ver."},
            {"role":"user", "content": f"{question}\n\nBelge:\n{text}"}
        ]
    )
    answer = response.choices[0].message.content
    return {"answer": answer}
