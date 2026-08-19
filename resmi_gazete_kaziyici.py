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
from urllib.parse import urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KUYRUK_KLASORU = "kuyruk"
os.makedirs(KUYRUK_KLASORU, exist_ok=True)

# ----------------- YARDIMCI FONKSİYONLAR -----------------

def metin_temizle(metin):
    metin = re.sub(r'\s+', ' ', metin)
    metin = metin.strip(" -\r\n")
    return metin

def get_arsiv_durumu():
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url: return None
    
    state_url = api_url.replace("/api/ingest", "/api/state")
    try:
        r = requests.get(state_url, timeout=15)
        if r.status_code == 200:
            return r.json().get("en_eski_kazinan_tarih")
    except Exception as e:
        print(f"[UYARI] Ubuntu'dan geçmiş tarih sorgulanamadı: {str(e)}")
    return None

# ----------------- KÖPRÜ VE GİT YÖNETİMİ -----------------

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
        pass

def veri_gonder(payload, dosya_yolu=None):
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url:
        return False
        
    try:
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[BAŞARILI] {payload['tarih']} verileri Ana PC'ye mühürlendi.")
            if dosya_yolu and os.path.exists(dosya_yolu):
                git_sil_push(dosya_yolu)
            return True
    except Exception as e:
        print(f"[UYARI] Ana PC'ye anlık ulaşılamadı, veri kuyruğa alınıyor...")
        
    if dosya_yolu is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_yolu = os.path.join(KUYRUK_KLASORU, f"kuyruk_{payload['tarih']}_{timestamp}.json")
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        git_commit_push(dosya_yolu)
    return False

def kuyrugu_isle():
    dosyalar = glob.glob(os.path.join(KUYRUK_KLASORU, "*.json"))
    if dosyalar:
        for dosya in dosyalar:
            with open(dosya, "r", encoding="utf-8") as f:
                payload = json.load(f)
            veri_gonder(payload, dosya_yolu=dosya)

# ----------------- ANA KAZIMA MOTORU -----------------

def gunu_kazi(tarih_obj, deneme_sayisi=1):
    tarih_str = tarih_obj.strftime("%Y%m%d")
    yil = tarih_obj.strftime("%Y")
    ay = tarih_obj.strftime("%m")
    
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        
        if response.status_code != 200:
            print(f"[UYARI] {tarih_obj.strftime('%Y-%m-%d')} tarihli Resmi Gazete bulunamadı.")
            return True 
            
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'windows-1254'
        soup = BeautifulSoup(response.text, 'html.parser')
        veriler = []
        
        for item in soup.find_all(['h2', 'h3', 'a'], href=True):
            text = metin_temizle(item.get_text())
            if text and len(text) > 5:
                link = urljoin("https://www.resmigazete.gov.tr", item['href'])
                veriler.append({"baslik": text, "link": link})
                
        if not veriler:
            return True
            
        payload = {
            "source": "resmi_gazete_gercek",
            "tarih": tarih_obj.strftime("%Y-%m-%d"),
            "toplanan_icerik_sayisi": len(veriler),
            "veriler": veriler
        }
        
        veri_gonder(payload)
        return True
        
    except requests.exceptions.Timeout:
        # Eğer sunucu yanıtsız kalırsa, 3 defaya kadar tekrar dener
        if deneme_sayisi <= 3:
            bekleme = 15 * deneme_sayisi # Her denemede bekleme süresini artır
            print(f"[UYARI] Sunucu zaman aşımı! {bekleme} saniye beklenip tekrar deneniyor... (Deneme {deneme_sayisi}/3)")
            time.sleep(bekleme)
            return gunu_kazi(tarih_obj, deneme_sayisi + 1)
        else:
            print(f"[HATA] {tarih_str} için maksimum deneme sayısına ulaşıldı, atlanıyor.")
            return False
            
    except Exception as e:
        print(f"[HATA] {tarih_str} kazınırken beklenmeyen hata: {str(e)}")
        return False

def kazima_islem():
    baslangic_zamani = time.time()
    MAX_SURE = 4.5 * 3600 
    
    kuyrugu_isle() 
    
    bugun = datetime.now()
    print(f"[BİLGİ] Güncel tarih kazınıyor: {bugun.strftime('%Y-%m-%d')}")
    gunu_kazi(bugun)
    
    en_eski_tarih_str = get_arsiv_durumu()
    if not en_eski_tarih_str:
        en_eski_tarih_str = bugun.strftime("%Y-%m-%d")
        
    hedef_tarih = datetime.strptime(en_eski_tarih_str, "%Y-%m-%d") - timedelta(days=1)
    print(f"[BİLGİ] Geçmiş tarama {hedef_tarih.strftime('%Y-%m-%d')} tarihinden itibaren geriye sarıyor...")
    
    while True:
        gecen_sure = time.time() - baslangic_zamani
        if gecen_sure >= MAX_SURE:
            print("[BİLGİ] Çalışma sınırına ulaşıldı. İşlem durduruluyor.")
            break
            
        if hedef_tarih.strftime("%Y-%m-%d") <= "1921-02-07":
            print("[BİLGİ] ARŞİV TAMAMLANDI.")
            break
            
        gunu_kazi(hedef_tarih)
        
        # SUNUCUYU YORMAMAK İÇİN RASTGELE BEKLEME SÜRESİ
        uyku_suresi = random.uniform(3.0, 6.0)
        print(f"      -> Sisteme nefes aldırılıyor... ({uyku_suresi:.1f} sn bekleme)")
        time.sleep(uyku_suresi)
        
        hedef_tarih -= timedelta(days=1)

if __name__ == "__main__":
    kazima_islem()
