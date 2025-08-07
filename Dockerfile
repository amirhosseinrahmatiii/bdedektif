FROM mcr.microsoft.com/azure-functions/python:4-python3.10

# ODBC ve diğer bağımlılıkları yükle
RUN apt-get update && \
    apt-get install -y unixodbc-dev gcc g++ curl && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18

# Gereken Python paketleri
WORKDIR /home/site/wwwroot
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Tüm uygulamayı kopyala
COPY . .

# Başlatıcı komut
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app"]
