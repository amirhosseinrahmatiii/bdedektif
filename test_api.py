#!/usr/bin/env python3
"""
Belge Dedektif API Test Scripti
Bu script API'nin çalışıp çalışmadığını test eder.
"""

import requests
import json
import os
from io import BytesIO

# API base URL
BASE_URL = "http://localhost:8000"

def test_health_endpoint():
    """Sağlık kontrolü endpoint'ini test eder"""
    print("🔍 Sağlık kontrolü testi...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Sağlık kontrolü başarılı!")
            print(f"📊 Yanıt: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        else:
            print(f"❌ Sağlık kontrolü başarısız! Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")

def test_root_endpoint():
    """Ana endpoint'i test eder"""
    print("\n🔍 Ana endpoint testi...")
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("✅ Ana endpoint başarılı!")
            print(f"📊 Yanıt: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        else:
            print(f"❌ Ana endpoint başarısız! Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")

def create_test_txt_file():
    """Test için basit bir TXT dosyası oluşturur"""
    test_content = """Bu bir test dosyasıdır.
Belge Dedektif API'sinin TXT dosya okuma özelliğini test etmek için oluşturulmuştur.
İçerisinde Türkçe karakterler de bulunmaktadır: ğüşıöç
Bu metin Azure Blob Storage'a yüklenecek ve analiz edilecektir."""
    
    with open("test_document.txt", "w", encoding="utf-8") as f:
        f.write(test_content)
    
    return "test_document.txt"

def test_upload_analyze_endpoint():
    """Dosya yükleme ve analiz endpoint'ini test eder"""
    print("\n🔍 Dosya yükleme ve analiz testi...")
    
    # Test dosyası oluştur
    test_file = create_test_txt_file()
    
    try:
        with open(test_file, 'rb') as f:
            files = [('files', (test_file, f, 'text/plain'))]
            response = requests.post(f"{BASE_URL}/upload-analyze", files=files)
        
        if response.status_code == 200:
            print("✅ Dosya yükleme ve analiz başarılı!")
            result = response.json()
            print(f"📊 İşlenen dosya sayısı: {result.get('processed_count', 0)}")
            print(f"📊 Hata sayısı: {result.get('error_count', 0)}")
            
            if result.get('results'):
                for file_result in result['results']:
                    print(f"\n📄 Dosya: {file_result.get('filename')}")
                    print(f"📊 Durum: {file_result.get('status')}")
                    print(f"📊 Dosya türü: {file_result.get('file_type')}")
                    print(f"📊 Dosya boyutu: {file_result.get('file_size')} byte")
                    print(f"📊 Çıkarılan metin uzunluğu: {file_result.get('text_length')} karakter")
                    if file_result.get('blob_url'):
                        print(f"🔗 Blob URL: {file_result.get('blob_url')}")
                    
                    # İlk 100 karakteri göster
                    extracted_text = file_result.get('extracted_text', '')
                    if extracted_text:
                        preview = extracted_text[:100] + "..." if len(extracted_text) > 100 else extracted_text
                        print(f"📝 Çıkarılan metin (önizleme): {preview}")
        else:
            print(f"❌ Dosya yükleme başarısız! Status: {response.status_code}")
            print(f"📊 Hata mesajı: {response.text}")
    
    except Exception as e:
        print(f"❌ Test hatası: {e}")
    
    finally:
        # Test dosyasını temizle
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"🧹 Test dosyası temizlendi: {test_file}")

def main():
    """Ana test fonksiyonu"""
    print("🚀 Belge Dedektif API Test Başlatılıyor...\n")
    
    # Tüm testleri çalıştır
    test_root_endpoint()
    test_health_endpoint()
    test_upload_analyze_endpoint()
    
    print("\n✨ Test tamamlandı!")

if __name__ == "__main__":
    main()

