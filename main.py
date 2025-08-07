from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
print("Static dosya yolu:", static_dir, flush=True)

# Sadece /static altına static dosyaları bağla
app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

# Anasayfa otomatik olarak index.html olsun:
from fastapi.responses import FileResponse

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

# API endpointleri çalışacak:
@app.post("/upload-analyze")
def upload_analyze():
    # ...
    pass

@app.get("/records")
def list_records():
    # ...
    pass
