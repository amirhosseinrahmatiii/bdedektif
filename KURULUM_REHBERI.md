# Belge Dedektif API - Kurulum Rehberi

## 📋 Proje Özeti

Bu proje, PDF, DOCX, TXT ve görsel dosyaları (JPG/PNG) analiz eden FastAPI tabanlı bir web servisidir. Dosyalar Azure Blob Storage'a kaydedilir ve görsel dosyalar Azure Cognitive Services OCR ile işlenir.

## 🛠️ Gereksinimler

- Python 3.10 veya üzeri
- Azure hesabı (Blob Storage ve Cognitive Services)
- İnternet bağlantısı

## 📁 Proje Yapısı

```
belge-dedektif-api/
├── main.py              # Ana FastAPI uygulaması
├── requirements.txt     # Python bağımlılıkları
├── .env                # Azure yapılandırma dosyası
└── KURULUM_REHBERI.md  # Bu dosya
```

## 🚀 Adım Adım Kurulum

### 1. Proje Klasörünü Oluşturun

```bash
mkdir belge-dedektif-api
cd belge-dedektif-api
```

### 2. Python Sanal Ortamı Oluşturun (Önerilen)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# veya
venv\Scripts\activate     # Windows
```

### 3. Gerekli Dosyaları Oluşturun

#### requirements.txt dosyası:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-dotenv==1.0.0
azure-storage-blob==12.19.0
python-docx==1.1.0
PyPDF2==3.0.1
requests==2.31.0
python-multipart==0.0.6
azure-cognitiveservices-vision-computervision==0.9.0
msrest==0.7.1
```

#### .env dosyası:
```
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=bdedek1754383290;AccountKey=mQSH2nF0xvcPEOT69xYOQpL799f68Cv+DK3D/JaD+AXH5IrMRw22FmclJM/ij96gJPpC98O6I4Fq+ASt0tDmqQ==;BlobEndpoint=https://bdedek1754383290.blob.core.windows.net/;FileEndpoint=https://bdedek1754383290.file.core.windows.net/;QueueEndpoint=https://bdedek1754383290.queue.core.windows.net/;TableEndpoint=https://bdedek1754383290.table.core.windows.net/
AZURE_CONTAINER_NAME=belgededektif
AZURE_OCR_ENDPOINT=https://swedencentral.api.cognitive.microsoft.com/
AZURE_OCR_KEY=fa4aff334e0e40dd8de707585db43243
```

### 4. Bağımlılıkları Yükleyin

```bash
pip install -r requirements.txt
```

### 5. Uygulamayı Başlatın

```bash
python main.py
```

Alternatif olarak uvicorn ile:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 🔧 API Kullanımı

### Ana Endpoint'ler

1. **Ana Sayfa**: `GET /`
2. **Sağlık Kontrolü**: `GET /health`
3. **Dosya Yükleme ve Analiz**: `POST /upload-analyze`

### Dosya Yükleme Örneği

#### cURL ile:
```bash
curl -X POST "http://localhost:8000/upload-analyze" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "files=@example.pdf" \
     -F "files=@example.docx"
```

#### Python ile:
```python
import requests

url = "http://localhost:8000/upload-analyze"
files = [
    ('files', ('example.pdf', open('example.pdf', 'rb'), 'application/pdf')),
    ('files', ('example.docx', open('example.docx', 'rb'), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'))
]

response = requests.post(url, files=files)
print(response.json())
```

### Desteklenen Dosya Türleri

- **PDF**: `.pdf`
- **Word Belgesi**: `.docx`
- **Metin Dosyası**: `.txt`
- **Görsel Dosyalar**: `.jpg`, `.jpeg`, `.png`

## 📊 API Yanıt Formatı

```json
{
  "message": "2 dosya işlendi",
  "processed_count": 2,
  "error_count": 0,
  "results": [
    {
      "filename": "example.pdf",
      "status": "success",
      "file_type": "pdf",
      "file_size": 12345,
      "blob_url": "https://bdedek1754383290.blob.core.windows.net/belgededektif/...",
      "extracted_text": "Dosyadan çıkarılan metin...",
      "text_length": 150,
      "upload_timestamp": "2025-08-06T09:43:07.272053"
    }
  ]
}
```

## 🔒 Güvenlik Notları

- `.env` dosyasını asla version control'e eklemeyin
- Azure anahtarlarınızı güvenli tutun
- Production ortamında CORS ayarlarını kısıtlayın

## 🚀 Deployment Seçenekleri

### Azure App Service

1. Azure CLI ile giriş yapın:
```bash
az login
```

2. Resource group oluşturun:
```bash
az group create --name belge-dedektif-rg --location "West Europe"
```

3. App Service plan oluşturun:
```bash
az appservice plan create --name belge-dedektif-plan --resource-group belge-dedektif-rg --sku B1 --is-linux
```

4. Web app oluşturun:
```bash
az webapp create --resource-group belge-dedektif-rg --plan belge-dedektif-plan --name belge-dedektif-api --runtime "PYTHON|3.11"
```

5. Kodu deploy edin:
```bash
az webapp up --name belge-dedektif-api --resource-group belge-dedektif-rg
```

### Docker ile

1. Dockerfile oluşturun:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

2. Docker image oluşturun:
```bash
docker build -t belge-dedektif-api .
```

3. Container'ı çalıştırın:
```bash
docker run -p 8000:8000 --env-file .env belge-dedektif-api
```

## 🐛 Sorun Giderme

### Yaygın Hatalar

1. **Azure bağlantı hatası**: `.env` dosyasındaki bilgileri kontrol edin
2. **OCR hatası**: Azure Cognitive Services anahtarının geçerli olduğundan emin olun
3. **Dosya yükleme hatası**: Dosya boyutunu ve türünü kontrol edin

### Log Kontrolü

Uygulama loglarını görmek için:
```bash
python main.py
```

## 📞 Destek

Herhangi bir sorun yaşarsanız:
1. Hata mesajını kontrol edin
2. Azure servislerinin aktif olduğundan emin olun
3. Bağımlılıkların doğru yüklendiğini kontrol edin

## 📝 Lisans

Bu proje MIT lisansı altında lisanslanmıştır.

