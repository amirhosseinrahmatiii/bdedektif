#!/usr/bin/env python3
import requests
import json
import os

BASE_URL = "http://localhost:8000"

def test_health_endpoint():
    print("🔍 Sağlık kontrolü testi...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}, Response: {response.json()}")
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")

def test_root_endpoint():
    print("\n🔍 Ana endpoint testi...")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")

def create_test_txt_file():
    test_content = "Deneme dosyası.\nBelge Dedektif test upload."
    test_file = "test_document.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_content)
    return test_file

def test_upload_analyze_endpoint():
    print("\n🔍 Dosya yükleme ve analiz testi...")
    test_file = create_test_txt_file()
    try:
        with open(test_file, "rb") as f:
            files = [("files", (test_file, f, "text/plain"))]
            response = requests.post(f"{BASE_URL}/upload-analyze", files=files)
        print(f"Status: {response.status_code}, Response: {response.json()}")
    except Exception as e:
        print(f"❌ Test hatası: {e}")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"🧹 Test dosyası temizlendi: {test_file}")

def main():
    print("🚀 Belge Dedektif API Test Başlatılıyor...\n")
    test_root_endpoint()
    test_health_endpoint()
    test_upload_analyze_endpoint()
    print("\n✨ Test tamamlandı!")

if __name__ == "__main__":
    main()
