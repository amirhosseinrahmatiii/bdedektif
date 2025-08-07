import os
import io
import uuid
import time
import re
from typing import List
from datetime import datetime
from collections import defaultdict

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials

import PyPDF2
from docx import Document
import openai
from dotenv import load_dotenv

# .env yükle
load_dotenv()
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Blob ve ComputerVision istemcileri
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
computervision_client = ComputerVisionClient(
    AZURE_OCR_ENDPOINT, CognitiveServicesCredentials(AZURE_OCR_KEY)
)

app = FastAPI(title="Belge Dedektif API", description="PDF, DOCX, TXT ve görsel dosyaları analiz eden API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

# RAM'de belge store
document_store = defaultdict(dict)

def extract_vat_amount(text):
    match = re.search(r'KDV[:\s%]*(\d+)', text, re.IGNORECASE)
    return match.group(1) if match else ""
def extract_total_amount(text):
    match = re.search(r'Toplam[^0-9]*([\d.,]+)', text, re.IGNORECASE)
    return match.group(1) if match else ""

def extract_text_from_pdf(file_content: bytes) -> str:
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
    text = ""
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()
def extract_text_from_docx(file_content: bytes) -> str:
    doc = Document(io.BytesIO(file_content))
    return "\n".join(p.text for p in doc.paragraphs)
def extract_text_from_txt(file_content: bytes) -> str:
    try:
        return file_content.decode('utf-8').strip()
    except UnicodeDecodeError:
        return file_content.decode('latin-1').strip()
async def extract_text_from_image_ocr(file_content: bytes) -> str:
    read_response = computervision_client.read_in_stream(io.BytesIO(file_content), raw=True)
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

@app.post("/upload-analyze")
async def upload_and_analyze_document(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="En az bir dosya yüklenmeli")
    results = []
    for file in files:
        file_content = await file.read()
        file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if file_extension not in ["pdf", "docx", "txt", "jpg", "jpeg", "png"]:
            results.append({
                "filename": file.filename, "status": "error",
                "error": "Desteklenmeyen dosya türü. Sadece PDF, DOCX, TXT, JPG, PNG dosyaları kabul edilir."
            })
            continue
        # Blob'a yükle
        unique_filename = f"{uuid.uuid4()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"
        blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=unique_filename)
        blob_client.upload_blob(file_content, content_type=file.content_type or "application/octet-stream", overwrite=True)
        blob_url = blob_client.url
        # Metin çıkar
        if file_extension == "pdf":
            extracted_text = extract_text_from_pdf(file_content)
        elif file_extension == "docx":
            extracted_text = extract_text_from_docx(file_content)
        elif file_extension == "txt":
            extracted_text = extract_text_from_txt(file_content)
        elif file_extension in ["jpg", "jpeg", "png"]:
            extracted_text = await extract_text_from_image_ocr(file_content)
        else:
            extracted_text = ""
        doc_id = str(uuid.uuid4())
        # Otomatik analiz: KDV/TOPLAM
        kdv = extract_vat_amount(extracted_text)
        total = extract_total_amount(extracted_text)
        document_store[doc_id] = {
            "filename": file.filename,
            "text": extracted_text,
            "blob_url": blob_url,
            "kdv": kdv,
            "total": total,
            "upload_timestamp": datetime.now().isoformat()
        }
        results.append({
            "id": doc_id,
            "filename": file.filename,
            "status": "success",
            "file_type": file_extension,
            "file_size": len(file_content),
            "blob_url": blob_url,
            "extracted_text": extracted_text,
            "kdv": kdv,
            "total": total,
            "text_length": len(extracted_text),
            "upload_timestamp": document_store[doc_id]["upload_timestamp"]
        })
    return {
        "message": f"{len(files)} dosya işlendi",
        "results": results
    }

@app.post("/ask")
async def ask_question(doc_id: str, question: str):
    if doc_id not in document_store:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")
    content = document_store[doc_id]["text"]
    prompt = (
        f"Kullanıcı yüklediği bir belgeden şunu soruyor:\n"
        f"Belge içeriği (OCR veya doküman metni):\n{content}\n"
        f"Soru: {question}\n"
        "Lütfen net, kısa ve anlaşılır şekilde cevap ver."
    )
    completion = openai.chat.completions.create(
        model="gpt-3.5-turbo",   # veya gpt-4o (anahtarın destekliyorsa)
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0
    )
    answer = completion.choices[0].message.content
    return {"answer": answer}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
