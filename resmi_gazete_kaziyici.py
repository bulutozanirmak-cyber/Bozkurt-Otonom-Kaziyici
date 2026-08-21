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
import pymupdf

# Görünmez Tarayıcı (Selenium) Kütüphaneleri
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KUYRUK_KLASORU = "kuyruk"
os.makedirs(KUYRUK_KLASORU, exist_ok=True)

# --- TARAYICI BAŞLATMA ---
def tarayici_baslat():
    """Arka planda gizli bir Google Chrome açar."""
    print("[BİLGİ] Görünmez tarayıcı (Selenium) yedek güç olarak başlatılıyor...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# --- METİN VE PDF İŞLEME FONKSİYONLARI ---

def metin_temizle(metin):
    if not metin:
        return ""
    metin = re.sub(r'\s+', ' ', metin)
    return metin.strip(" -\r\n")

def pdf_metnini_cek(pdf_linki):
    """Tier 1: PDF dosyasını indirip PyMuPDF ile okumaya çalışır."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(pdf_linki, headers=headers, verify=False, timeout=15)
        if r.status_code == 200 and 'application/pdf' in r.headers.get('Content-Type', '').lower():
            doc = pymupdf.open(stream=r.content, filetype="pdf")
            metin = ""
            for page in doc:
                metin += page.get_text("text") + " "
            return metin_temizle(metin)
    except:
        pass
    return None

def gorunmez_tarayici_ile_cek(link, driver):
    """Tier 2: Sayfaya bir insan gibi girip ekrandaki metni kopyalar."""
    try:
        driver.get(link)
        time.sleep(3)
        metin = driver.find_element(By.TAG_NAME, "body").text
        temiz_metin = metin_temizle(metin)
        if len(temiz_metin) > 10:
            return temiz_metin
        else:
            return "[HATA: Görünmez tarayıcı ekranda okunabilir bir metin bulamadı.]"
    except Exception as e:
        return f"[TARAYICI_HATASI: {str(e)}]"

def alt_sayfa_isle(link, driver):
    """İki aşamalı hibrit okuma yöneticisi."""
    pdf_linki = link.lower().replace('.htm', '.pdf')
    if "main.aspx" in pdf_linki and "main=" in pdf_linki:
        match = re.search(r'main=([^&]+)', pdf_linki)
        if match:
            pdf_linki = match.group(1)
            
    tam_metin = pdf_metnini_cek(pdf_linki)
    
    if not tam_metin or len(tam_metin) < 10:
        print("      -> Hızlı yol başarısız. Görünmez tarayıcı devreye giriyor...")
        tam_metin = gorunmez_tarayici_ile_cek(link, driver)
        
    return tam_metin

# --- HABERLEŞME VE ARŞİV KONTROLÜ (Eksik olan fonksiyon eklendi) ---

def get_arsiv_durumu():
    """Ubuntu'dan veya yerel state'den en eski tarihi sorgular."""
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url: 
        return None
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
    if not api_url: 
        # API yoksa GitHub kuyruğunda sakla
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_yolu = os.path.join(KUYRUK_KLASORU, f"kuyruk_{payload['tarih']}_{timestamp}.json")
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        git_islem(dosya_yolu, "ekle")
        return True

    try:
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[BAŞARILI] {payload['tarih']} verileri mühürlendi.")
            if dosya_yolu: 
                git_islem(dosya_yolu, "sil")
            return True
    except:
        pass
    return False

# --- ANA KAZIMA DÖNGÜSÜ ---

def gunu_kazi(tarih_obj, driver):
    tarih_str = tarih_obj.strftime("%Y%m%d")
    yil = tarih_obj.strftime("%Y")
    ay = tarih_obj.strftime("%m")
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    headers = {"User-Agent": "Mozilla/5.0"}
    
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
                link = urljoin(url, href) if 'urljoin' in globals() else f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{href}"
                
                if "resmigazete.gov.tr" in link:
                    print(f"[KAZIMA] Okunuyor: {text[:40]}...")
                    tam_metin = alt_sayfa_isle(link, driver)
                    
                    veriler.append({
                        "kategori": mevcut_kategori,
                        "baslik": text,
                        "link": link, 
                        "tam_metin": tam_metin
                    })
                
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
    except Exception as e:
        print(f"[HATA] {tarih_str} işlenirken hata: {str(e)}")
        return False

def kazima_islem():
    baslangic_zamani = time.time()
    MAX_SURE = 4.5 * 3600 
    
    driver = tarayici_baslat()
    
    dosyalar = glob.glob(os.path.join(KUYRUK_KLASORU, "*.json"))
    for dosya in dosyalar:
        with open(dosya, "r", encoding="utf-8") as f:
            veri_gonder(json.load(f), dosya_yolu=dosya)
            
    bugun = datetime.now()
    gunu_kazi(bugun, driver)
    
    en_eski_tarih_str = get_arsiv_durumu()
    if not en_eski_tarih_str:
        en_eski_tarih_str = bugun.strftime("%Y-%m-%d")
        
    hedef_tarih = datetime.strptime(en_eski_tarih_str, "%Y-%m-%d") - timedelta(days=1)
    
    while True:
        if (time.time() - baslangic_zamani) >= MAX_SURE:
            break
        if hedef_tarih.strftime("%Y-%m-%d") <= "1921-02-07":
            break
            
        gunu_kazi(hedef_tarih, driver)
        time.sleep(random.uniform(2.0, 4.0)) 
        hedef_tarih -= timedelta(days=1)
        
    driver.quit()

if __name__ == "__main__":
    kazima_islem()
