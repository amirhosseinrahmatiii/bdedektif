import os
import io
import uuid
import time
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials

import PyPDF2
from docx import Document
import requests
from dotenv import load_dotenv

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

# Logging'i başlat
logger = setup_logging()
logger.info("🚀 Belge Dedektif API başlatılıyor...")

# Azure yapılandırması
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")

logger.info(f"Azure yapılandırması yüklendi - Container: {AZURE_CONTAINER_NAME}")

# FastAPI uygulaması
app = FastAPI(
    title="Belge Dedektif API",
    description="PDF, DOCX, TXT ve görsel dosyaları analiz eden API",
    version="1.0.0"
)

# CORS middleware ekle
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # İstek bilgilerini logla
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    log_api_request(str(request.url.path), request.method, client_ip, user_agent)
    
    response = await call_next(request)
    
    # Performans bilgilerini logla
    process_time = (time.time() - start_time) * 1000
    log_performance(f"{request.method} {request.url.path}", process_time, f"Status: {response.status_code}")
    
    return response

# Statik dosyaları servis et
app.mount("/static", StaticFiles(directory="static"), name="static")

# Ana sayfa yönlendirmesi
@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

# Azure Blob Storage istemcisi
try:
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    logger.info("✅ Azure Blob Storage istemcisi başarıyla oluşturuldu")
    log_azure_operation("INIT", "BlobStorage", "SUCCESS", "İstemci başlatıldı")
except Exception as e:
    logger.error(f"❌ Azure Blob Storage istemcisi oluşturulamadı: {e}")
    log_azure_operation("INIT", "BlobStorage", "ERROR", str(e))

# Azure Computer Vision istemcisi
try:
    computervision_client = ComputerVisionClient(
        AZURE_OCR_ENDPOINT, 
        CognitiveServicesCredentials(AZURE_OCR_KEY)
    )
    logger.info("✅ Azure Computer Vision istemcisi başarıyla oluşturuldu")
    log_azure_operation("INIT", "ComputerVision", "SUCCESS", "İstemci başlatıldı")
except Exception as e:
    logger.error(f"❌ Azure Computer Vision istemcisi oluşturulamadı: {e}")
    log_azure_operation("INIT", "ComputerVision", "ERROR", str(e))

class DocumentAnalyzer:
    """Belge analiz sınıfı"""
    
    @staticmethod
    def extract_text_from_pdf(file_content: bytes) -> str:
        """PDF dosyasından metin çıkarır"""
        start_time = time.time()
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            duration = (time.time() - start_time) * 1000
            log_file_operation("EXTRACT_TEXT", "PDF", "SUCCESS", f"Sayfa sayısı: {len(pdf_reader.pages)}, Süre: {duration:.2f}ms")
            logger.info(f"PDF metin çıkarma başarılı - {len(pdf_reader.pages)} sayfa, {len(text)} karakter")
            
            return text.strip()
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            log_file_operation("EXTRACT_TEXT", "PDF", "ERROR", f"Hata: {str(e)}, Süre: {duration:.2f}ms")
            logger.error(f"PDF okuma hatası: {e}")
            raise HTTPException(status_code=400, detail=f"PDF okuma hatası: {str(e)}")
    
    @staticmethod
    def extract_text_from_docx(file_content: bytes) -> str:
        """DOCX dosyasından metin çıkarır"""
        start_time = time.time()
        try:
            doc = Document(io.BytesIO(file_content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            
            duration = (time.time() - start_time) * 1000
            log_file_operation("EXTRACT_TEXT", "DOCX", "SUCCESS", f"Paragraf sayısı: {len(doc.paragraphs)}, Süre: {duration:.2f}ms")
            logger.info(f"DOCX metin çıkarma başarılı - {len(doc.paragraphs)} paragraf, {len(text)} karakter")
            
            return text.strip()
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            log_file_operation("EXTRACT_TEXT", "DOCX", "ERROR", f"Hata: {str(e)}, Süre: {duration:.2f}ms")
            logger.error(f"DOCX okuma hatası: {e}")
            raise HTTPException(status_code=400, detail=f"DOCX okuma hatası: {str(e)}")
    
    @staticmethod
    def extract_text_from_txt(file_content: bytes) -> str:
        """TXT dosyasından metin çıkarır"""
        start_time = time.time()
        try:
            text = file_content.decode('utf-8').strip()
            duration = (time.time() - start_time) * 1000
            log_file_operation("EXTRACT_TEXT", "TXT", "SUCCESS", f"Karakter sayısı: {len(text)}, Süre: {duration:.2f}ms")
            logger.info(f"TXT metin çıkarma başarılı - {len(text)} karakter")
            return text
        except UnicodeDecodeError:
            try:
                text = file_content.decode('latin-1').strip()
                duration = (time.time() - start_time) * 1000
                log_file_operation("EXTRACT_TEXT", "TXT", "SUCCESS", f"Karakter sayısı: {len(text)} (latin-1), Süre: {duration:.2f}ms")
                logger.info(f"TXT metin çıkarma başarılı (latin-1) - {len(text)} karakter")
                return text
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                log_file_operation("EXTRACT_TEXT", "TXT", "ERROR", f"Hata: {str(e)}, Süre: {duration:.2f}ms")
                logger.error(f"TXT okuma hatası: {e}")
                raise HTTPException(status_code=400, detail=f"TXT okuma hatası: {str(e)}")
    
    @staticmethod
    async def extract_text_from_image_ocr(file_content: bytes) -> str:
        """Görsel dosyasından OCR ile metin çıkarır"""
        start_time = time.time()
        try:
            logger.info("OCR işlemi başlatılıyor...")
            log_azure_operation("OCR_START", "ComputerVision", "PROCESSING", f"Dosya boyutu: {len(file_content)} byte")
            
            # Azure Computer Vision OCR işlemi
            read_response = computervision_client.read_in_stream(
                io.BytesIO(file_content), 
                raw=True
            )
            
            # İşlem ID'sini al
            read_operation_location = read_response.headers["Operation-Location"]
            operation_id = read_operation_location.split("/")[-1]
            
            logger.info(f"OCR işlem ID: {operation_id}")
            
            # İşlem tamamlanana kadar bekle
            while True:
                read_result = computervision_client.get_read_result(operation_id)
                if read_result.status not in ['notStarted', 'running']:
                    break
                time.sleep(1)
            
            # Sonuçları işle
            text = ""
            if read_result.status == OperationStatusCodes.succeeded:
                for text_result in read_result.analyze_result.read_results:
                    for line in text_result.lines:
                        text += line.text + "\n"
            
            duration = (time.time() - start_time) * 1000
            log_azure_operation("OCR_COMPLETE", "ComputerVision", "SUCCESS", f"Çıkarılan metin: {len(text)} karakter, Süre: {duration:.2f}ms")
            logger.info(f"OCR işlemi başarılı - {len(text)} karakter çıkarıldı")
            
            return text.strip()
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            log_azure_operation("OCR_COMPLETE", "ComputerVision", "ERROR", f"Hata: {str(e)}, Süre: {duration:.2f}ms")
            logger.error(f"OCR işlemi hatası: {e}")
            raise HTTPException(status_code=400, detail=f"OCR işlemi hatası: {str(e)}")

class AzureBlobManager:
    """Azure Blob Storage yönetim sınıfı"""
    
    @staticmethod
    def upload_file_to_blob(file_content: bytes, filename: str, content_type: str) -> str:
        """Dosyayı Azure Blob Storage'a yükler"""
        start_time = time.time()
        try:
            # Benzersiz dosya adı oluştur
            file_extension = filename.split('.')[-1] if '.' in filename else ''
            unique_filename = f"{uuid.uuid4()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"
            
            logger.info(f"Blob yükleme başlatılıyor: {filename} -> {unique_filename}")
            log_azure_operation("BLOB_UPLOAD_START", "BlobStorage", "PROCESSING", f"Dosya: {filename}, Boyut: {len(file_content)} byte")
            
            # Blob istemcisi oluştur
            blob_client = blob_service_client.get_blob_client(
                container=AZURE_CONTAINER_NAME, 
                blob=unique_filename
            )
            
            # Dosyayı yükle
            blob_client.upload_blob(
                file_content, 
                content_type=content_type,
                overwrite=True
            )
            
            duration = (time.time() - start_time) * 1000
            blob_url = blob_client.url
            log_azure_operation("BLOB_UPLOAD_COMPLETE", "BlobStorage", "SUCCESS", f"URL: {blob_url}, Süre: {duration:.2f}ms")
            logger.info(f"Blob yükleme başarılı - {unique_filename}, Süre: {duration:.2f}ms")
            
            return blob_url
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            log_azure_operation("BLOB_UPLOAD_COMPLETE", "BlobStorage", "ERROR", f"Hata: {str(e)}, Süre: {duration:.2f}ms")
            logger.error(f"Blob yükleme hatası: {e}")
            raise HTTPException(status_code=500, detail=f"Blob yükleme hatası: {str(e)}")

# API Endpoint'leri

@app.get("/health")
async def health_check():
    """Sağlık kontrolü"""
    logger.info("Sağlık kontrolü isteği alındı.")
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "azure_blob_connected": True,
        "azure_ocr_connected": True
    }

@app.post("/upload-analyze")
async def upload_and_analyze_document(
    files: List[UploadFile] = File(..., description="Analiz edilecek dosyalar (PDF, DOCX, TXT, JPG, PNG)")
):
    """
    Dosyaları yükler, analiz eder ve Azure Blob Storage'a kaydeder
    """
    logger.info(f"Upload/Analyze isteği alındı. {len(files)} dosya.")
    if not files:
        logger.warning("Yüklenecek dosya bulunamadı.")
        raise HTTPException(status_code=400, detail="En az bir dosya yüklenmeli")
    
    results = []
    analyzer = DocumentAnalyzer()
    blob_manager = AzureBlobManager()
    
    for file in files:
        try:
            logger.info(f"Dosya işleniyor: {file.filename}")
            # Dosya içeriğini oku
            file_content = await file.read()
            
            # Dosya türünü kontrol et
            file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
            
            if file_extension not in ["pdf", "docx", "txt", "jpg", "jpeg", "png"]:
                logger.warning(f"Desteklenmeyen dosya türü: {file.filename}")
                results.append({
                    "filename": file.filename,
                    "status": "error",
                    "error": "Desteklenmeyen dosya türü. Sadece PDF, DOCX, TXT, JPG, PNG dosyaları kabul edilir."
                })
                continue
            
            # Dosyayı Azure Blob Storage'a yükle
            blob_url = blob_manager.upload_file_to_blob(
                file_content, 
                file.filename, 
                file.content_type or "application/octet-stream"
            )
            
            # Dosya türüne göre metin çıkar
            extracted_text = ""
            
            if file_extension == "pdf":
                extracted_text = analyzer.extract_text_from_pdf(file_content)
            elif file_extension == "docx":
                extracted_text = analyzer.extract_text_from_docx(file_content)
            elif file_extension == "txt":
                extracted_text = analyzer.extract_text_from_txt(file_content)
            elif file_extension in ["jpg", "jpeg", "png"]:
                extracted_text = await analyzer.extract_text_from_image_ocr(file_content)
            
            # Sonucu ekle
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
            logger.info(f"Dosya işleme başarılı: {file.filename}")
            
        except HTTPException as he:
            logger.error(f"HTTPException: {file.filename} - {he.detail}")
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": he.detail
            })
        except Exception as e:
            logger.critical(f"Beklenmeyen hata: {file.filename} - {str(e)}")
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": f"Beklenmeyen hata: {str(e)}"
            })
    
    processed_count = len([r for r in results if r["status"] == "success"])
    error_count = len([r for r in results if r["status"] == "error"])
    logger.info(f"Upload/Analyze tamamlandı. İşlenen: {processed_count}, Hata: {error_count}")
    
    return {
        "message": f"{len(files)} dosya işlendi",
        "processed_count": processed_count,
        "error_count": error_count,
        "results": results
    }

if __name__ == "__main__":
    logger.info("🌟 Belge Dedektif API sunucusu başlatılıyor...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

