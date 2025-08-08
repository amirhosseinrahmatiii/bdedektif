from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pyodbc

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# SQL bağlantı ayarlarını DÜZENLE
SQL_CONN_STR = "Driver={ODBC Driver 17 for SQL Server};Server=bdedeksql1754383472.database.windows.net;Database=belgededektifdb;Uid=sqladmin;Pwd=Kav1234!;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"

class GlobalQuestion(BaseModel):
    question: str

@app.post("/ask-global")
async def ask_global(q: GlobalQuestion):
    try:
        conn = pyodbc.connect(SQL_CONN_STR)
        cursor = conn.cursor()
        qlower = q.question.lower()
        # Basit örnekler (daha fazlası eklenebilir)
        if "toplam kdv" in qlower or ("kdv" in qlower and "toplam" in qlower):
            cursor.execute("SELECT SUM(TRY_CAST(KDV as float)) FROM Belgeler WHERE ISNUMERIC(KDV)=1")
            result = cursor.fetchone()[0]
            if result is not None:
                return {"answer": f"Toplam KDV: {result:.2f} ₺"}
            else:
                return {"answer": "Toplam KDV verisi yok."}
        if "bu ay" in qlower and "toplam" in qlower:
            import datetime
            ay = datetime.datetime.now().strftime("%Y-%m")
            cursor.execute("SELECT SUM(TRY_CAST(Toplam as float)) FROM Belgeler WHERE Tarih LIKE ?", (ay + "%",))
            result = cursor.fetchone()[0]
            if result is not None:
                return {"answer": f"Bu ay toplam harcamanız: {result:.2f} ₺"}
            else:
                return {"answer": "Bu aya ait harcama verisi yok."}
        # Daha fazla örnek: "Bu hafta", "Son 3 ay" vs eklenebilir
        return {"answer": "Şu an bu soruya otomatik yanıt verilemiyor."}
    except Exception as ex:
        return {"answer": f"Hata oluştu: {ex}"}

@app.get("/list-docs")
def list_docs():
    try:
        conn = pyodbc.connect(SQL_CONN_STR)
        cursor = conn.cursor()
        cursor.execute("SELECT Ad, Tarih, Firma, KDV, Toplam, OCR, BlobURL FROM Belgeler ORDER BY id DESC")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
        data = [dict(zip(cols, row)) for row in rows]
        return JSONResponse(data)
    except Exception as ex:
        return JSONResponse([])

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # Kısa, örnek upload endpoint (buraya AI/analiz/BlobStorage vs. kendi upload logic'in eklenebilir)
    return {"message": f"{file.filename} başarıyla yüklendi (demo endpoint)"}
