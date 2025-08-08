import os
import datetime
from typing import List, Any, Dict

import pyodbc
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

APP_NAME = "BelgeDedektif API"
APP_VERSION = "0.1.0"

app = FastAPI(title=APP_NAME, version=APP_VERSION)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SQL Bağlantısı ---
def _build_sql_conn_str() -> str:
    # Önce doğrudan connection string var mı bak
    direct = os.getenv("SQL_CONN_STR")
    if direct:
        return direct

    # Yoksa parçalı env değişkenlerinden oluştur
    server = os.getenv("SQL_SERVER", "bdedeksql1754383472.database.windows.net")
    db = os.getenv("SQL_DB", "belgededektifdb")
    user = os.getenv("SQL_USER", "sqladmin")
    pwd = os.getenv("SQL_PASSWORD", "Kav12345!")  # ENV'den gelmezse bu varsayılanı kullanır
    return (
        "Driver={ODBC Driver 17 for SQL Server};"
        f"Server={server};Database={db};Uid={user};Pwd={pwd};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )

SQL_CONN_STR = _build_sql_conn_str()

def get_conn():
    return pyodbc.connect(SQL_CONN_STR)

# --- Modeller ---
class GlobalQuestion(BaseModel):
    question: str

# --- Kök & Sağlık ---
@app.get("/")
def root():
    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}

@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "healthy"}
    except Exception as ex:
        return JSONResponse(status_code=500, content={"status": "unhealthy", "error": str(ex)})

# --- Soru-Cevap (örnek) ---
@app.post("/ask-global")
async def ask_global(q: GlobalQuestion):
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            qlower = q.question.lower()

            # Toplam KDV
            if "toplam kdv" in qlower or ("kdv" in qlower and "toplam" in qlower):
                cursor.execute("""
                    SELECT SUM(TRY_CONVERT(decimal(18,2), KDV))
                    FROM dbo.Belgeler
                """)
                result = cursor.fetchone()[0]
                return {"answer": f"Toplam KDV: {result:.2f} ₺"} if result is not None else {"answer": "Toplam KDV verisi yok."}

            # Bu ay toplam
            if "bu ay" in qlower and "toplam" in qlower:
                ay = datetime.datetime.now().strftime("%Y-%m")
                cursor.execute("""
                    SELECT SUM(TRY_CONVERT(decimal(18,2), Toplam))
                    FROM dbo.Belgeler
                    WHERE CONVERT(varchar(7), TRY_CONVERT(date, Tarih), 23) = ?
                """, ay)
                result = cursor.fetchone()[0]
                return {"answer": f"Bu ay toplam harcamanız: {result:.2f} ₺"} if result is not None else {"answer": "Bu aya ait harcama verisi yok."}

        return {"answer": "Şu an bu soruya otomatik yanıt verilemiyor."}
    except Exception as ex:
        return {"answer": f"Hata oluştu: {ex}"}

# --- Belge Listeleme ---
@app.get("/list-docs")
def list_docs():
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, Ad, Tarih, Firma, KDV, Toplam, OCR, BlobURL
                FROM dbo.Belgeler
                ORDER BY Id DESC
            """)
            rows = cursor.fetchall()
            cols = [c[0] for c in cursor.description]
            data: List[Dict[str, Any]] = [dict(zip(cols, row)) for row in rows]
            return JSONResponse(content=data)
    except Exception as ex:
        return JSONResponse(status_code=500, content={"error": str(ex), "data": []})

# --- Upload (demo) ---
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # Burada istersen Azure Blob'a kaydetme/AI OCR akışını ekleyebiliriz.
    return {"message": f"{file.filename} başarıyla yüklendi (demo endpoint)"}

# --- Lokal geliştirme için ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
