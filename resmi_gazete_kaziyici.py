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
from urllib.parse import urljoin

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
    chrome_options.add_argument("--headless") # Ekransız çalışma
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# --- METİN İŞLEME VE KAZIMA FONKSİYONLARI ---

def metin_temizle(metin):
    if not metin:
        return ""
    metin = re.sub(r'\s+', ' ', metin)
    return metin.strip(" -\r\n")

def pdf_metnini_cek(pdf_linki):
    """Tier 1 (Hızlı Yol): PDF dosyasını indirip PyMuPDF ile okumaya çalışır."""
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
    return None # Hızlı yol başarısız olursa None döner ki Selenium devreye girsin.

def görünmez_tarayici_ile_cek(link, driver):
    """Tier 2 (Kaba Kuvvet): Sayfaya bir insan gibi girip ekrandaki metni kopyalar."""
    try:
        driver.get(link)
        time.sleep(3) # Sayfanın ve arkadaki PDF okuyucunun (pdf.js) yüklenmesi için 3 saniye bekle
        
        # Ekrandaki tüm metni al
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
    # Adım 1: Hızlı yolu dene (.pdf üreterek)
    pdf_linki = link.lower().replace('.htm', '.pdf')
    if "main.aspx" in pdf_linki and "main=" in pdf_linki:
        match = re.search(r'main=([^&]+)', pdf_linki)
        if match:
            pdf_linki = match.group(1)
            
    tam_metin = pdf_metnini_cek(pdf_linki)
    
    # Adım 2: Hızlı yol işe yaramadıysa (None döndüyse), Görünmez Tarayıcıyı kullan
    if not tam_metin or len(tam_metin) < 10:
        print("      -> Hızlı yol başarısız. Görünmez tarayıcı (Kaba Kuvvet) devreye giriyor...")
        tam_metin = görünmez_tarayici_ile_cek(link, driver)
        
    return tam_metin

# --- HABERLEŞME (Bu kısımlar standart) ---

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
            if dosya_yolu: git_islem(dosya_yolu, "sil")
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

# --- ANA DÖNGÜ ---

def gunu_kazi(tarih_obj, driver):
    tarih_str = tarih_obj.strftime("%Y%m%d")
    yil = tarih_obj.strftime("%Y")
    ay = tarih_obj.strftime("%m")
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        if response.status_code != 200: return True 
            
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
                link = urljoin(url, href)
                
                if "resmigazete.gov.tr" in link:
                    print(f"[KAZIMA] Okunuyor: {text[:40]}...")
                    
                    tam_metin = alt_sayfa_isle(link, driver)
                    
                    veriler.append({
                        "kategori": mevcut_kategori,
                        "baslik": text,
                        "link": link, 
                        "tam_metin": tam_metin
                    })
                
        if not veriler: return True
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
    MAX_SURE = 4.5 * 3600 # 4.5 Saatlik güvenlik sınırı
    
    # 1. Tarayıcıyı başlat
    driver = tarayici_baslat()
    
    # 2. Varsa önceki günlerden kalan kuyruğu erit
    dosyalar = glob.glob(os.path.join(KUYRUK_KLASORU, "*.json"))
    for dosya in dosyalar:
        with open(dosya, "r", encoding="utf-8") as f:
            veri_gonder(json.load(f), dosya_yolu=dosya)
            
    # 3. Her zaman önce bugünü kazı
    bugun = datetime.now()
    gunu_kazi(bugun, driver)
    
    # 4. Arşiv durumunu öğren ve geriye doğru taramaya başla
    en_eski_tarih_str = get_arsiv_durumu()
    if not en_eski_tarih_str:
        en_eski_tarih_str = bugun.strftime("%Y-%m-%d")
        
    hedef_tarih = datetime.strptime(en_eski_tarih_str, "%Y-%m-%d") - timedelta(days=1)
    
    print(f"[BİLGİ] Otonom geriye dönük tarama başlıyor. Hedef: {hedef_tarih.strftime('%Y-%m-%d')}")
    
    # 5. Süre dolana kadar veya arşiv bitene kadar geriye doğru git
    while True:
        if (time.time() - baslangic_zamani) >= MAX_SURE:
            print("[BİLGİ] GitHub maksimum çalışma süresine yaklaştı. Görev güvenle devrediliyor.")
            break
        if hedef_tarih.strftime("%Y-%m-%d") <= "1921-02-07":
            print("[BİLGİ] Bütün arşiv tarandı.")
            break
            
        gunu_kazi(hedef_tarih, driver)
        time.sleep(random.uniform(2.0, 4.0)) # Ban yememek için rastgele mola
        hedef_tarih -= timedelta(days=1)
        
    # 6. Tarayıcıyı kapat
    driver.quit()

if __name__ == "__main__":
    kazima_islem()
