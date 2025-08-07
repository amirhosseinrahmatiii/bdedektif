from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os

app = FastAPI()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
print("Static dosya yolu:", static_dir, flush=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

# --- ÖRNEK: Basit in-memory veri saklama ---
FILES = []

@app.post("/upload-analyze")
async def upload_analyze(file: UploadFile = File(...)):
    # Basit dosya kaydetme ve veri analizi simülasyonu
    content = await file.read()
    # Sadece isim, boyut ve dummy verisi
    info = {
        "filename": file.filename,
        "size": len(content),
        "total": 123.45,     # Demo: Gerçek KDV/Toplam yok, örnek değer!
        "vat": 23.45,
        "date": "2025-08-07",
        "vendor": "DEMO VENDOR"
    }
    FILES.append(info)
    return {"message": "Yüklendi", "result": info}

@app.get("/records")
def records():
    return {"records": FILES}
