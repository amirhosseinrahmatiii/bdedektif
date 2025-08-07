import os
import io
import uuid
import time
from typing import List
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials

import PyPDF2
from docx import Document

# Logging yapılandırması
from logging_config import (
    setup_logging, 
    log_file_operation, 
    log_azure_operation, 
    log_api_request, 
    log_performance
)

# .env dosyasını yükle
load_dotenv()
logger = setup_logging()

# Azure yapılandırması
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")

# FastAPI uygulaması
app = FastAPI(
    title="Belge Dedektif API",
    description="PDF, DOCX, TXT ve görsel dosyaları analiz eden API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statik dosya servis
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

# Azure servisleri başlat
try:
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
except Exception as e:
    logger.error(f"Azure Blob Storage hatası: {e}")

try:
    computervision_client = ComputerVisionClient(
        AZURE_OCR_ENDPOINT, 
        CognitiveServicesCredentials(AZURE_OCR_KEY)
    )
except Exception as e:
    logger.error(f"Azure Computer Vision hatası: {e}")

# Yardımcı sınıflar
class DocumentAnalyzer:
    @staticmethod
    def extract_text_from_pdf(file_content: bytes) -> str:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()

    @staticmethod
    def extract_text_from_docx(file_content: bytes) -> str:
        doc = Document(io.BytesIO(file_content))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()

    @staticmethod
    def extract_text_from_txt(file_content: bytes) -> str:
        try:
            return file_content.decode('utf-8').strip()
        except UnicodeDecodeError:
            return file_content.decode('latin-1').strip()

    @staticmethod
    async def extract_text_from_image_ocr(file_content: bytes) -> str:
        read_response = computervision_client.read_in_stream(
            io.BytesIO(file_content), raw=True
        )
        read_operation_location = read_response.headers["Operation-Location"]
        operation_id = read_operation_location.split("/")[-1]
        while True:
            read_result = computervision_client.get_read_result(operation_id)
            if read_result.status not in ['notStarted', 'running']:
                break
            time.sleep(1)
        text = ""
        if read_result.status == OperationStatusCodes.succeeded:
            for text_result in read_result.analyze_result.read_results:
                for line in text_result.lines:
                    text += line.text + "\n"
        return text.strip()

class AzureBlobManager:
    @staticmethod
    def upload_file_to_blob(file_content: bytes, filename: str, content_type: str) -> str:
        file_extension = filename.split('.')[-1] if '.' in filename else ''
        unique_filename = f"{uuid.uuid4()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"
        blob_client = blob_service_client.get_blob_client(
            container=AZURE_CONTAINER_NAME, 
            blob=unique_filename
        )
        blob_client.upload_blob(file_content, content_type=content_type, overwrite=True)
        return blob_client.url

# API endpoint
@app.post("/upload-analyze")
async def upload_and_analyze_document(
    files: List[UploadFile] = File(...)
):
    results = []
    analyzer = DocumentAnalyzer()
    blob_manager = AzureBlobManager()
    for file in files:
        file_content = await file.read()
        file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if file_extension not in ["pdf", "docx", "txt", "jpg", "jpeg", "png"]:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": "Desteklenmeyen dosya türü."
            })
            continue
        blob_url = blob_manager.upload_file_to_blob(
            file_content, 
            file.filename, 
            file.content_type or "application/octet-stream"
        )
        extracted_text = ""
        if file_extension == "pdf":
            extracted_text = analyzer.extract_text_from_pdf(file_content)
        elif file_extension == "docx":
            extracted_text = analyzer.extract_text_from_docx(file_content)
        elif file_extension == "txt":
            extracted_text = analyzer.extract_text_from_txt(file_content)
        elif file_extension in ["jpg", "jpeg", "png"]:
            extracted_text = await analyzer.extract_text_from_image_ocr(file_content)
        results.append({
            "filename": file.filename,
            "status": "success",
            "file_type": file_extension,
            "file_size": len(file_content),
            "blob_url": blob_url,
            "extracted_text": extracted_text,
            "text_length": len(extracted_text),
            "upload_timestamp": datetime.now().isoformat()
        })
    return {
        "message": f"{len(files)} dosya işlendi",
        "results": results
    }

# Sağlık kontrolü
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
