FROM python:3.10-slim

# Azure'un beklediği çalışma dizini
WORKDIR /home/site/wwwroot

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodunu kopyala
COPY . .

# Port ayarı
EXPOSE 8000

# Uygulamayı başlat
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app", "--timeout", "600"]
