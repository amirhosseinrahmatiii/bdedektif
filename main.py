from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os

app = FastAPI()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

# Sağlık kontrolü için endpoint
@app.get("/health")
def health():
    return {"status": "ok"}

# Bellekte dosya kayıtlarını tutmak için (örnek/demo amaçlı)
FILES = []

@app.post("/upload-analyze")
async def upload_analyze(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        content = await file.read()
        info = {
            "filename": file.filename,
            "status": "success",
            "file_type": file.content_type,
            "file_size": len(content),
            "text_length": len(content),
            "blob_url": "",  # Demo amaçlı boş
            "extracted_text": content.decode(errors="ignore")[:200],  # Sadece ilk 200 karakteri tutuyoruz
            "total_amount": 123.45,     # Demo
            "vat_amount": 23.45,
            "vendor_name": "DEMO VENDOR"
        }
        FILES.append(info)
        results.append(info)
    return {
        "message": f"{len(results)} dosya işlendi.",
        "results": results,
        "processed_count": len(results),
        "error_count": 0
    }

@app.get("/records")
def records():
    return {"records": FILES}
