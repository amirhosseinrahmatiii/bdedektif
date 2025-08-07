from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

# Her platformda static klasörünü bulur
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
print("Static dosya yolu:", static_dir, flush=True)

# Ana dizine static klasörü bağla, index.html anasayfa olur
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# (Opsiyonel) Örnek API endpointi
@app.get("/api/hello")
def hello():
    return {"msg": "Merhaba, API çalışıyor!"}
