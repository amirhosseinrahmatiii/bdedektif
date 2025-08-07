import os
import io
import re
import random
import datetime
import time
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from azure.storage.blob import BlobServiceClient
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
import pyodbc
import openai

app = FastAPI()

# Ortam değişkenlerinden yapılandırma oku
AZURE_OCR_ENDPOINT = os.getenv('AZURE_OCR_ENDPOINT')
AZURE_OCR_KEY = os.getenv('AZURE_OCR_KEY')
AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME')
SQL_SERVER = os.getenv('SQL_SERVER')
SQL_DB = os.getenv('SQL_DB')
SQL_USER = os.getenv('SQL_USER')
SQL_PASSWORD = os.getenv('SQL_PASSWORD')
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

if not AZURE_OCR_ENDPOINT or not AZURE_OCR_KEY or not AZURE_STORAGE_CONNECTION_STRING:
    raise RuntimeError('Missing Azure OCR or Storage configuration')

blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
try:
    container_client.create_container()
except Exception:
    pass

cv_client = None
if AZURE_OCR_ENDPOINT and AZURE_OCR_KEY:
    cv_client = ComputerVisionClient(AZURE_OCR_ENDPOINT, CognitiveServicesCredentials(AZURE_OCR_KEY))

conn_str = (
    f'Driver={{ODBC Driver 17 for SQL Server}};Server={SQL_SERVER};Database={SQL_DB};'
    f'Uid={SQL_USER};Pwd={SQL_PASSWORD};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
)
try:
    conn = pyodbc.connect(conn_str, autocommit=True)
except Exception as e:
    raise RuntimeError(f'Database connection failed: {e}')
cursor = conn.cursor()
try:
    cursor.execute(
        "CREATE TABLE invoices (id INT IDENTITY(1,1) PRIMARY KEY, user_id NVARCHAR(100), file_name NVARCHAR(255), "
        "blob_url NVARCHAR(500), extracted_text NVARCHAR(MAX), total_amount DECIMAL(10,2), vat_amount DECIMAL(10,2), "
        "vendor_name NVARCHAR(255), uploaded_at DATETIME DEFAULT GETDATE())"
    )
except Exception as e:
    if 'There is already an object named' not in str(e):
        print(f'Error creating table: {e}')

DEFAULT_USER = 'demo_user'
DOCUMENTS = {}

def parse_invoice_text(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total_amount = None
    vat_amount = 0.0
    vendor_name = ''
    for i, line in enumerate(lines):
        if line.upper().startswith('T.C.') or 'TURKIYE' in line.upper():
            continue
        if any(keyword in line.upper() for keyword in ['BIRIM', 'BAKANLI', 'MUDURLUGU']):
            continue
        if re.search(r'[0-9]{3,}', line):
            if len(re.findall(r'\d', line)) > 4:
                continue
        if any(word in line.upper() for word in ['SOKAK', 'CAD', 'NO:', 'NO ']):
            continue
        if i < len(lines) - 1 and any(keyword in lines[i+1].upper() for keyword in ['BIRIM', 'BAKANLI', 'MUDURLUGU']):
            if len(line.split()) <= 2:
                continue
        vendor_name = line
        break
    total_pattern = re.compile(r'(toplam|total)', re.IGNORECASE)
    total_line = None
    for line in lines:
        if 'GENEL TOPLAM' in line.upper():
            total_line = line
            break
    if total_line is None:
        candidates = [l for l in lines if total_pattern.search(l)]
        if candidates:
            total_line = candidates[-1]
    if total_line:
        nums = re.findall(r'[0-9]+[\.,][0-9]+|[0-9]+', total_line)
        if nums:
            total_str = nums[-1]
            total_str = re.sub(r'[^0-9,\.]', '', total_str)
            if total_str:
                if ',' in total_str and '.' in total_str:
                    total_str = total_str.replace('.', '').replace(',', '.')
                elif ',' in total_str:
                    total_str = total_str.replace(',', '.')
                try:
                    total_amount = float(total_str)
                except:
                    total_amount = None
    vat_amount = 0.0
    for line in lines:
        if 'KDV' in line.upper() or 'VAT' in line.upper():
            nums = re.findall(r'[0-9]+[\.,][0-9]+|[0-9]+', line)
            if nums:
                vat_str = nums[-1]
                vat_str = re.sub(r'[^0-9,\.]', '', vat_str)
                if vat_str:
                    if ',' in vat_str and '.' in vat_str:
                        vat_str = vat_str.replace('.', '').replace(',', '.')
                    elif ',' in vat_str:
                        vat_str = vat_str.replace(',', '.')
                    try:
                        amount = float(vat_str)
                    except:
                        amount = 0.0
                    vat_amount += amount
    if total_amount is None:
        total_amount = 0.0
    return total_amount, vat_amount, vendor_name

@app.post('/upload-analyze')
async def upload_analyze(files: list[UploadFile] = File(...)):
    results = []
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail='No files uploaded')
    for file in files:
        file_bytes = await file.read()
        file_name = file.filename
        file_size = len(file_bytes)
        file_type = file.content_type or ''
        status = 'success'
        extracted_text = ''
        total_amount = 0.0
        vat_amount = 0.0
        vendor_name = ''
        try:
            if cv_client:
                read_response = cv_client.read_in_stream(io.BytesIO(file_bytes), raw=True)
                operation_location = read_response.headers.get('Operation-Location')
                if not operation_location:
                    raise Exception('No Operation-Location returned from OCR API')
                operation_id = operation_location.split('/')[-1]
                for attempt in range(10):
                    result = cv_client.get_read_result(operation_id)
                    if result.status.lower() not in ['notstarted', 'running']:
                        break
                    time.sleep(1)
                if result.status.lower() != 'succeeded':
                    raise Exception('OCR processing failed or timed out')
                text_parts = []
                for page in result.analyze_result.read_results:
                    for line in page.lines:
                        text_parts.append(line.text)
                extracted_text = '\n'.join(text_parts)
            else:
                raise Exception('OCR client not initialized')
        except Exception:
            status = 'error'
            extracted_text = ''
        if extracted_text:
            total_amount, vat_amount, vendor_name = parse_invoice_text(extracted_text)
        else:
            total_amount, vat_amount, vendor_name = 0.0, 0.0, ''
        blob_name = f"{DEFAULT_USER}_{int(time.time()*1000)}_{random.randint(0,9999)}_{file_name}"
        try:
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(file_bytes, overwrite=True)
            blob_url = blob_client.url
        except Exception:
            status = 'error'
            blob_url = ''
        record_id = None
        try:
            cursor.execute("""INSERT INTO invoices (user_id, file_name, blob_url, extracted_text, total_amount, vat_amount, vendor_name) 
                               OUTPUT Inserted.id 
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                           (DEFAULT_USER, file_name, blob_url, extracted_text, total_amount, vat_amount, vendor_name))
            row = cursor.fetchone()
            if row:
                record_id = int(row[0])
        except Exception as e:
            print(f'DB insert error: {e}')
        # AI için kaydet (yalnızca test fazı için; kalıcı DB'de olması önerilir)
        DOCUMENTS[file_name] = {
            "extracted_text": extracted_text,
            "blob_url": blob_url
        }
        results.append({
            'id': record_id,
            'file_name': file_name,
            'status': status,
            'file_type': file_type,
            'file_size': file_size,
            'blob_url': blob_url,
            'extracted_text': extracted_text,
            'total_amount': total_amount,
            'vat_amount': vat_amount,
            'vendor_name': vendor_name
        })
    message = f"{len(files)} dosya işlendi."
    return {'message': message, 'results': results}

@app.get('/summary')
def get_summary():
    user = DEFAULT_USER
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    total_sum = 0.0
    total_vat = 0.0
    try:
        cursor.execute("SELECT ISNULL(SUM(total_amount),0), ISNULL(SUM(vat_amount),0) FROM invoices WHERE user_id=? AND YEAR(uploaded_at)=? AND MONTH(uploaded_at)=?", (user, year, month))
        row = cursor.fetchone()
        if row:
            total_sum = float(row[0]) if row[0] is not None else 0.0
            total_vat = float(row[1]) if row[1] is not None else 0.0
    except Exception as e:
        print(f'Error querying totals: {e}')
    top_vendors = []
    try:
        cursor.execute("SELECT TOP 3 vendor_name, COUNT(*) as cnt FROM invoices WHERE user_id=? AND YEAR(uploaded_at)=? AND MONTH(uploaded_at)=? GROUP BY vendor_name ORDER BY cnt DESC", (user, year, month))
        rows = cursor.fetchall()
        for r in rows:
            name = r[0] or ''
            count = int(r[1])
            top_vendors.append({'vendor': name, 'count': count})
    except Exception as e:
        print(f'Error querying top vendors: {e}')
    return {
        'total_sum_month': total_sum,
        'total_vat_month': total_vat,
        'top_vendors_month': top_vendors
    }

@app.get('/records')
def list_records():
    user = DEFAULT_USER
    records = []
    try:
        cursor.execute("SELECT id, file_name, total_amount, vat_amount, vendor_name, uploaded_at FROM invoices WHERE user_id=? ORDER BY uploaded_at DESC", (user,))
        rows = cursor.fetchall()
        for r in rows:
            records.append({
                'id': int(r[0]),
                'file_name': r[1],
                'total_amount': float(r[2]) if r[2] is not None else 0.0,
                'vat_amount': float(r[3]) if r[3] is not None else 0.0,
                'vendor_name': r[4] or '',
                'uploaded_at': r[5].strftime('%Y-%m-%d %H:%M:%S') if r[5] else None
            })
    except Exception as e:
        print(f'Error querying records: {e}')
    return {'records': records}

@app.delete('/delete')
def delete_record(id: int):
    user = DEFAULT_USER
    try:
        cursor.execute("SELECT blob_url FROM invoices WHERE id=? AND user_id=?", (id, user))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Record not found')
        blob_url = row[0] or ''
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Database error: {e}')
    blob_name = ''
    try:
        if blob_url:
            parts = blob_url.split('/')
            if len(parts) >= 5:
                blob_name = '/'.join(parts[4:])
    except Exception as e:
        print(f'Error parsing blob URL: {e}')
    if blob_name:
        try:
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Failed to delete file from storage: {e}')
    try:
        cursor.execute("DELETE FROM invoices WHERE id=? AND user_id=?", (id, user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete record from database: {e}')
    return {'message': 'Deleted successfully.'}

@app.post('/update')
async def update_record(id: int, file: UploadFile = File(...)):
    user = DEFAULT_USER
    try:
        cursor.execute("SELECT blob_url FROM invoices WHERE id=? AND user_id=?", (id, user))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Record not found')
        old_blob_url = row[0] or ''
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Database error: {e}')
    new_bytes = await file.read()
    new_name = file.filename
    new_type = file.content_type or ''
    new_size = len(new_bytes)
    status = 'success'
    extracted_text = ''
    total_amount = 0.0
    vat_amount = 0.0
    vendor_name = ''
    try:
        if cv_client:
            read_response = cv_client.read_in_stream(io.BytesIO(new_bytes), raw=True)
            operation_location = read_response.headers.get('Operation-Location')
            if not operation_location:
                raise Exception('No Operation-Location from OCR API')
            operation_id = operation_location.split('/')[-1]
            for attempt in range(10):
                result = cv_client.get_read_result(operation_id)
                if result.status.lower() not in ['notstarted', 'running']:
                    break
                time.sleep(1)
            if result.status.lower() != 'succeeded':
                raise Exception('OCR processing failed or timed out')
            text_parts = []
            for page in result.analyze_result.read_results:
                for line in page.lines:
                    text_parts.append(line.text)
            extracted_text = '\n'.join(text_parts)
        else:
            raise Exception('OCR client not initialized')
    except Exception:
        status = 'error'
        extracted_text = ''
    if extracted_text:
        total_amount, vat_amount, vendor_name = parse_invoice_text(extracted_text)
    else:
        total_amount, vat_amount, vendor_name = 0.0, 0.0, ''
    if old_blob_url:
        try:
            parts = old_blob_url.split('/')
            if len(parts) >= 5:
                old_blob_name = '/'.join(parts[4:])
                blob_client = container_client.get_blob_client(old_blob_name)
                blob_client.delete_blob()
        except Exception as e:
            print(f'Warning: could not delete old blob: {e}')
    new_blob_name = f"{DEFAULT_USER}_{int(time.time()*1000)}_{random.randint(0,9999)}_{new_name}"
    new_blob_url = ''
    try:
        new_blob_client = container_client.get_blob_client(new_blob_name)
        new_blob_client.upload_blob(new_bytes, overwrite=True)
        new_blob_url = new_blob_client.url
    except Exception as e:
        status = 'error'
    try:
        cursor.execute("UPDATE invoices SET file_name=?, blob_url=?, extracted_text=?, total_amount=?, vat_amount=?, vendor_name=? WHERE id=? AND user_id=?", 
                       (new_name, new_blob_url, extracted_text, total_amount, vat_amount, vendor_name, id, user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to update record in database: {e}')
    return {
        'id': id,
        'file_name': new_name,
        'status': status,
        'file_type': new_type,
        'file_size': new_size,
        'blob_url': new_blob_url,
        'extracted_text': extracted_text,
        'total_amount': total_amount,
        'vat_amount': vat_amount,
        'vendor_name': vendor_name
    }

# AI ile soru sor endpoint'i
@app.post("/ask")
async def ask_ai(filename: str, question: str):
    doc = DOCUMENTS.get(filename)
    if not doc or not doc.get("extracted_text"):
        raise HTTPException(status_code=404, detail="Belge bulunamadı veya analiz edilmemiş.")
    prompt = f"Bir kullanıcı sana şu belgeyi yükledi:\n---\n{doc['extracted_text']}\n---\nKullanıcının sorusu: {question}\nLütfen belgeye göre doğru ve kısa cevap ver."
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Kısa, doğru, sade bir cevap ver. Eğer belgeyle ilgili değilse, 'Belge içeriğinde bu bilgi yok' de."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.2
        )
        answer = response['choices'][0]['message']['content'].strip()
        return {"answer": answer}
    except Exception as e:
        return {"error": str(e)}

# Arayüz için statik dosyaları sun
app.mount('/', StaticFiles(directory='static', html=True), name='static')
