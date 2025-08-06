# Belge Dedektif API - Proje Özeti ve Azure Bilgileri

Bu belge, Belge Dedektif API projesinin temel gereksinimlerini, kurulum adımlarını ve Azure ile ilgili kritik bilgileri özetlemektedir. Bu bilgiler, projenin başka bir ekibe veya yapay zekaya devredilmesi durumunda hızlı bir başlangıç yapmalarını sağlamak amacıyla hazırlanmıştır.

## 📋 Proje Özeti

Belge Dedektif API, PDF, DOCX, TXT ve görsel (JPG/PNG) dosyalarını yükleyip analiz etmek için tasarlanmış bir FastAPI uygulamasıdır. Yüklenen tüm dosyalar Azure Blob Storage'a kaydedilirken, görsel dosyalar Azure Cognitive Services OCR kullanılarak metne dönüştürülür. API, herhangi bir ön yüz (frontend) gerektirmeyen, tamamen arka uç (backend) odaklı bir çözümdür.

## 🛠️ Gereksinimler

- **Python**: 3.9 veya üzeri
- **FastAPI**: `main.py` dosyasında tanımlanan ana uygulama
- **Bağımlılıklar**: `requirements.txt` dosyasında listelenen tüm kütüphaneler yüklü olmalıdır.
- **Dockerfile**: (Opsiyonel) Projeyi Docker container içinde çalıştırmak için mevcuttur.
- **.env dosyası**: Hassas Azure bağlantı bilgileri ve API anahtarları bu dosyada saklanır.
- **test_api.py**: Son kullanıcı testi ve API fonksiyonelliğini doğrulamak için bir test scripti.

### Azure Ortamı Bilgileri

Projenin çalışabilmesi için aşağıdaki Azure servislerine ve bilgilere erişim gereklidir:

- **Azure Blob Storage Bağlantı Bilgileri**:
  - `AZURE_STORAGE_CONNECTION_STRING`: `DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=bdedek1754383290;AccountKey=mQSH2nF0xvcPEOT69xYOQpL799f68Cv+DK3D/JaD+AXH5IrMRw22FmclJM/ij96gJPpC98O6I4Fq+ASt0tDmqQ==;BlobEndpoint=https://bdedek1754383290.blob.core.windows.net/;FileEndpoint=https://bdedek1754383290.file.core.windows.net/;QueueEndpoint=https://bdedek1754383290.queue.core.windows.net/;TableEndpoint=https://bdedek1754383290.table.core.windows.net/`
  - `AZURE_CONTAINER_NAME`: `belgededektif`

- **Azure OCR/Cognitive Services API Bilgileri**:
  - `AZURE_OCR_ENDPOINT`: `https://swedencentral.api.cognitive.microsoft.com/`
  - `AZURE_OCR_KEY`: `fa4aff334e0e40dd8de707585db43243`

## 🚀 Kurulum Adımları

1.  **Tüm Proje Dosyalarını Bir Klasöre Kopyalayın**: `belge-dedektif-api` klasörünün tüm içeriğini hedef ortama taşıyın.

2.  **Python Sanal Ortamı Oluşturun ve Aktive Edin**:
    ```bash
    python -m venv venv
    # Linux/Mac için:
    source venv/bin/activate
    # Windows için:
    venv\Scripts\activate
    ```

3.  **Python Bağımlılıklarını Yükleyin**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **.env Dosyasını Doldurun**: `belge-dedektif-api` klasöründeki `.env.example` dosyasını kopyalayarak `.env` adında yeni bir dosya oluşturun ve yukarıda belirtilen Azure bilgileriyle doldurun. **Bu bilgilerin gizli tutulması kritik öneme sahiptir.**

    ```env
    AZURE_STORAGE_CONNECTION_STRING=...
    AZURE_CONTAINER_NAME=...
    AZURE_OCR_ENDPOINT=...
    AZURE_OCR_KEY=...
    ```

5.  **FastAPI Uygulamasını Başlatın**:
    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```
    Uygulama `http://0.0.0.0:8000` adresinde çalışmaya başlayacaktır.

6.  **(Opsiyonel) Docker ile Çalıştırın**:
    Eğer Docker kullanmak isterseniz, proje dizininde aşağıdaki komutları çalıştırın:
    ```bash
    docker build -t belge-dedektif-api .
    docker run -p 8000:8000 --env-file .env belge-dedektif-api
    ```

7.  **Testleri Çalıştırın**:
    API'nin doğru çalıştığını doğrulamak için `test_api.py` scriptini çalıştırın:
    ```bash
    python test_api.py
    ```
    Bu script, ana endpoint, sağlık kontrolü ve dosya yükleme/analiz endpoint'lerini test edecektir.

## 💡 Sonraki Adımlar İçin Öneriler

-   **Production Ortamına Taşıma**: Azure App Service, Azure Container Instances veya Kubernetes gibi platformlara dağıtım.
-   **Frontend Entegrasyonu**: API'yi kullanacak bir web arayüzü (React, Vue, Angular vb.) geliştirme.
-   **Gerçek Veri Testleri**: Çeşitli ve büyük boyutlu gerçek dünya verileriyle kapsamlı testler yapma.
-   **Ek Belge Türleri**: XML, XLSX gibi farklı belge formatları için ayrıştırıcılar (parser) ekleme.
-   **Kullanıcı Doğrulama**: JWT veya Azure AD ile güvenli kullanıcı doğrulama mekanizmaları entegrasyonu.
-   **Gelişmiş İzleme**: Prometheus, Grafana gibi araçlarla performans ve hata izleme sistemleri kurma.

---

