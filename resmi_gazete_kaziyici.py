import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import urllib3
import glob
import subprocess
import time
import re
import random
import io
import pymupdf  # PDF okuma motorumuz
from urllib.parse import urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KUYRUK_KLASORU = "kuyruk"
os.makedirs(KUYRUK_KLASORU, exist_ok=True)

# --- METİN VE PDF İŞLEME FONKSİYONLARI ---

def metin_temizle(metin):
    if not metin:
        return ""
    metin = re.sub(r'\s+', ' ', metin)
    return metin.strip(" -\r\n")

def pdf_metnini_cek(pdf_linki):
    """
    Doğru adresi verilen PDF linkini indirir ve PyMuPDF kullanarak içindeki saf metni çıkarır.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(pdf_linki, headers=headers, verify=False, timeout=30)
        
        if r.status_code != 200 or 'application/pdf' not in r.headers.get('Content-Type', '').lower():
             return "[HATA: Orijinal PDF dosyasına ulaşılamadı. Sadece HTML formatında olabilir.]"

        doc = pymupdf.open(stream=r.content, filetype="pdf")
        metin = ""
        for page in doc:
            metin += page.get_text("text") + " "
        
        temiz_metin = metin_temizle(metin)
        
        if len(temiz_metin) < 10:
            return "[PDF_BILGISI: Bu belge resim olarak taranmış, OCR (Görselden Metin Tanıma) gerekiyor.]"
            
        return temiz_metin
        
    except Exception as e:
        return f"[PDF_OKUMA_HATASI: Detay -> {str(e)}]"

# --- HABERLEŞME VE VERİ GÖNDERİMİ ---

def get_arsiv_durumu():
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url: return None
    state_url = api_url.replace("/api/ingest", "/api/state")
    try:
        r = requests.get(state_url, timeout=15)
        if r.status_code == 200:
            return r.json().get("en_eski_kazinan_tarih")
    except:
        pass
    return None

def git_islem(dosya_yolu, islem_tipi):
    try:
        if islem_tipi == "sil" and os.path.exists(dosya_yolu):
            os.remove(dosya_yolu)
        subprocess.run(["git", "config", "--global", "user.name", "Bozkurt Bot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@bozkurt.local"], check=True)
        subprocess.run(["git", "add", dosya_yolu], check=True)
        mesaj = "Otonom: Veri kuyruga eklendi" if islem_tipi == "ekle" else "Otonom: Kuyruk temizlendi"
        subprocess.run(["git", "commit", "-m", mesaj], check=True)
        subprocess.run(["git", "push"], check=True)
    except:
        pass

def veri_gonder(payload, dosya_yolu=None):
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url: return False
    
    try:
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[BAŞARILI] {payload['tarih']} verileri Ubuntu'ya mühürlendi.")
            if dosya_yolu:
                git_islem(dosya_yolu, "sil")
            return True
    except:
        pass
        
    if dosya_yolu is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_yolu = os.path.join(KUYRUK_KLASORU, f"kuyruk_{payload['tarih']}_{timestamp}.json")
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        git_islem(dosya_yolu, "ekle")
    return False

# --- ANA KAZIMA DÖNGÜSÜ ---

def gunu_kazi(tarih_obj, deneme_sayisi=1):
    tarih_str = tarih_obj.strftime("%Y%m%d")
    yil = tarih_obj.strftime("%Y")
    ay = tarih_obj.strftime("%m")
    
    # url: Bulunduğumuz günün dizini
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        if response.status_code != 200:
            return True 
            
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'windows-1254'
        soup = BeautifulSoup(response.text, 'html.parser')
        veriler = []
        mevcut_kategori = "GENEL"
        
        for element in soup.find_all(['h2', 'h3', 'h4', 'a'], href=True):
            tag_name = element.name
            text = metin_temizle(element.get_text())
            
            if tag_name in ['h2', 'h3', 'h4'] and len(text) > 3:
                mevcut_kategori = text
                continue
                
            if text and len(text) > 5:
                href = element['href']
                
                # HATA DÜZELTİLDİ: Sitenin ana domaini yerine, bulunduğumuz günün dizini ile (url) birleştiriyoruz.
                link = urljoin(url, href)
                
                # İLANLAR İÇİN DÜZELTME: Link karmaşık main.aspx yapısındaysa, asıl hedefi içinden çek.
                if "main.aspx" in link and "main=" in link:
                    match = re.search(r'main=([^&]+)', link)
                    if match:
                        link = match.group(1)
                
                if "resmigazete.gov.tr" in link:
                    print(f"[KAZIMA] PDF Aranıyor: {text[:40]}...")
                    
                    pdf_linki = link.lower().replace('.htm', '.pdf')
                    tam_metin = pdf_metnini_cek(pdf_linki)
                    
                    veriler.append({
                        "kategori": mevcut_kategori,
                        "baslik": text,
                        "link": link, 
                        "tam_metin": tam_metin
                    })
                    time.sleep(1.0) 
                
        if not veriler:
            return True
            
        payload = {
            "source": "resmi_gazete_llm_ready",
            "tarih": tarih_obj.strftime("%Y-%m-%d"),
            "toplanan_icerik_sayisi": len(veriler),
            "veriler": veriler
        }
        
        veri_gonder(payload)
        return True
        
    except requests.exceptions.Timeout:
        if deneme_sayisi <= 3:
            time.sleep(10 * deneme_sayisi)
            return gunu_kazi(tarih_obj, deneme_sayisi + 1)
        return False
    except Exception as e:
        print(f"[HATA] {tarih_str} işlenirken hata: {str(e)}")
        return False

def kazima_islem():
    # TEST AMAÇLI: Yalnızca hata aldığımız 11 Ağustos 2026'yı çalıştırıyoruz.
    test_tarihi = datetime.strptime("2026-08-11", "%Y-%m-%d")
    print(f"[TEST BAŞLIYOR] {test_tarihi.strftime('%Y-%m-%d')} tarihi için özel PDF taraması...")
    gunu_kazi(test_tarihi)
    print("[TEST BİTTİ]")

if __name__ == "__main__":
    kazima_islem()
