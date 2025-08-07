from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

# Dinamik static yolunu bul (her platformda çalışır)
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
print("Static dosya yolu:", static_dir, flush=True)

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# API örnek endpoint (opsiyonel)
@app.get("/api/hello")
def hello():
    return {"msg": "Merhaba, API çalışıyor!"}
