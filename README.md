# 📄 Belge Dedektif API

Azure Blob Storage ve OCR entegrasyonlu FastAPI tabanlı belge analiz servisi.

## 🚀 Özellikler

- **Çoklu Dosya Desteği**: PDF, DOCX, TXT ve görsel dosyaları (JPG/PNG)
- **Azure Entegrasyonu**: Blob Storage ve Cognitive Services OCR
- **RESTful API**: FastAPI ile modern API tasarımı
- **Otomatik Analiz**: Dosyalardan metin çıkarma ve analiz
- **Cloud Storage**: Tüm dosyalar Azure Blob Storage'da güvenle saklanır

## 📋 Desteklenen Dosya Türleri

| Dosya Türü | Uzantı | İşlem Türü |
|-------------|---------|------------|
| PDF | `.pdf` | Yerel metin çıkarma |
| Word Belgesi | `.docx` | Yerel metin çıkarma |
| Metin Dosyası | `.txt` | Doğrudan okuma |
| Görsel | `.jpg`, `.jpeg`, `.png` | Azure OCR |

## 🛠️ Hızlı Başlangıç

```bash
# Projeyi klonla
git clone <repo-url>
cd belge-dedektif-api

# Sanal ortam oluştur
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Bağımlılıkları yükle
pip install -r requirements.txt

# Çevre değişkenlerini ayarla
cp .env.example .env
# .env dosyasını Azure bilgilerinizle doldurun

# Uygulamayı başlat
python main.py
```

## 📚 API Kullanımı

### Dosya Yükleme

```bash
curl -X POST "http://localhost:8000/upload-analyze" \
     -H "Content-Type: multipart/form-data" \
     -F "files=@example.pdf" \
     -F "files=@example.docx"
```

### Python ile Kullanım

```python
import requests

url = "http://localhost:8000/upload-analyze"
files = [('files', open('example.pdf', 'rb'))]
response = requests.post(url, files=files)
print(response.json())
```

## 🔧 Yapılandırma

`.env` dosyasında aşağıdaki değişkenleri ayarlayın:

```env
AZURE_STORAGE_CONNECTION_STRING=your_connection_string
AZURE_CONTAINER_NAME=your_container_name
AZURE_OCR_ENDPOINT=your_ocr_endpoint
AZURE_OCR_KEY=your_ocr_key
```

## 🐳 Docker ile Çalıştırma

```bash
# Image oluştur
docker build -t belge-dedektif-api .

# Container çalıştır
docker run -p 8000:8000 --env-file .env belge-dedektif-api
```

## 🧪 Test

```bash
# API testlerini çalıştır
python test_api.py

# Sağlık kontrolü
curl http://localhost:8000/health
```

## 📖 Dokümantasyon

API dokümantasyonuna erişim:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 🚀 Deployment

### Azure App Service

```bash
az webapp up --name belge-dedektif-api --resource-group your-rg
```

### Docker Hub

```bash
docker tag belge-dedektif-api your-username/belge-dedektif-api
docker push your-username/belge-dedektif-api
```

## 🤝 Katkıda Bulunma

1. Fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit edin (`git commit -m 'Add amazing feature'`)
4. Push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

## 📄 Lisans

Bu proje MIT lisansı altında lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakın.

## 🆘 Destek

Sorun yaşıyorsanız:
- [Issues](../../issues) sayfasından yeni bir issue açın
- [Kurulum Rehberi](KURULUM_REHBERI.md) dosyasını inceleyin
- Test scriptini çalıştırın: `python test_api.py`

