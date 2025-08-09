# Python 3.10 tabanlı resmi imaj
FROM python:3.10-slim

# Ortam değişkenleri
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Çalışma dizini
WORKDIR /app

# Bağımlılıkların önce yüklenmesi (cache için)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodunun kopyalanması
COPY . .

# Port açma
EXPOSE $PORT

# Uygulamayı çalıştırma
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app", "--timeout", "600"]
