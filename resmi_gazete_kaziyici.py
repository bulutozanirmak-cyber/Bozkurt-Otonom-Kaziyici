import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import urllib3
import glob
import subprocess

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KUYRUK_KLASORU = "kuyruk"
os.makedirs(KUYRUK_KLASORU, exist_ok=True)

def git_commit_push(dosya_yolu):
    try:
        subprocess.run(["git", "config", "--global", "user.name", "Bozkurt Bot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@bozkurt.local"], check=True)
        subprocess.run(["git", "add", dosya_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Otonom: Cevrimdisi veri kuyruga eklendi"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("[BİLGİ] Veri çevrimdışı kuyruğa eklendi ve GitHub'a yedeklendi.")
    except Exception as e:
        print(f"[HATA] Git yedekleme başarısız: {str(e)}")

def git_sil_push(dosya_yolu):
    try:
        if os.path.exists(dosya_yolu):
            os.remove(dosya_yolu)
        subprocess.run(["git", "add", dosya_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Otonom: Basariyla gonderilen kuyruk temizlendi"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[HATA] Kuyruk temizleme hatası: {str(e)}")

def veri_gonder(payload, dosya_yolu=None):
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url:
        print("[HATA] BOZKURT_API_URL tanımlı değil!")
        return False
        
    try:
        print(f"[BİLGİ] Veriler Ana PC'ye fırlatılıyor ({api_url})...")
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code == 200:
            print("[BAŞARILI] Veriler Ana PC'ye mühürlendi.")
            if dosya_yolu and os.path.exists(dosya_yolu):
                git_sil_push(dosya_yolu)
            return True
        else:
            print(f"[HATA] Sunucu reddetti. Durum Kodu: {response.status_code}")
    except Exception as e:
        print(f"[KRİTİK HATA] Ana PC'ye ulaşılamadı: {str(e)}")
        
    if dosya_yolu is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_yolu = os.path.join(KUYRUK_KLASORU, f"kuyruk_{timestamp}.json")
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        git_commit_push(dosya_yolu)
    return False

def kuyrugu_isle():
    dosyalar = glob.glob(os.path.join(KUYRUK_KLASORU, "*.json"))
    if dosyalar:
        print(f"[BİLGİ] Kuyrukta bekleyen {len(dosyalar)} dosya işleniyor...")
        for dosya in dosyalar:
            with open(dosya, "r", encoding="utf-8") as f:
                payload = json.load(f)
            veri_gonder(payload, dosya_yolu=dosya)

def kazima_islem():
    kuyrugu_isle()
    
    bugun = datetime.now()
    tarih_str = bugun.strftime("%Y%m%d")
    yil = bugun.strftime("%Y")
    ay = bugun.strftime("%m")
    
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    print(f"[BİLGİ] {url} adresinden veriler çekiliyor...")
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        if response.status_code != 200:
            print(f"[UYARI] {tarih_str} tarihli Resmi Gazete henüz yayımlanmamış.")
            return

        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        veriler = []
        for item in soup.find_all(['h2', 'h3', 'a'], href=True):
            text = item.get_text(strip=True)
            if text and len(text) > 5:
                link = item['href']
                if not link.startswith('http'):
                    link = f"https://www.resmigazete.gov.tr{link}"
                veriler.append({"baslik": text, "link": link})
                
        payload = {
            "source": "resmi_gazete_gercek",
            "tarih": bugun.strftime("%Y-%m-%d"),
            "toplanan_icerik_sayisi": len(veriler),
            "veriler": veriler
        }
        
        veri_gonder(payload)
            
    except Exception as e:
        print(f"[KRİTİK HATA] Kazıma sırasında hata oluştu: {str(e)}")

if __name__ == "__main__":
    kazima_islem()
