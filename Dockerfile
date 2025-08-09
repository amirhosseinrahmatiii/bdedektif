FROM python:3.10-slim

# Çalışma dizinini Azure'ın beklediği şekilde ayarla
WORKDIR /home/site/wwwroot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app", "--timeout", "600"]
