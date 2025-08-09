# Dockerfile

# 1. Adım: Temel Python imajını kullan
FROM python:3.10-slim

# 2. Adım: Çalışma dizinini ayarla
WORKDIR /app

# 3. Adım: Bağımlılıkları kopyala ve kur
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Adım: Proje kodlarının tamamını kopyala
COPY . .

# 5. Adım: Uygulamanın çalışacağı portu belirt
EXPOSE 8000

# 6. Adım: Uygulamayı başlatma komutu
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--host", "0.0.0.0", "--port", "8000"]
