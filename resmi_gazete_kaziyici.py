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
from urllib.parse import urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KUYRUK_KLASORU = "kuyruk"
os.makedirs(KUYRUK_KLASORU, exist_ok=True)

def metin_temizle(metin):
    """Gereksiz boşlukları, HTML artıklarını ve kaçış karakterlerini temizler"""
    if not metin:
        return ""
    metin = re.sub(r'\s+', ' ', metin)
    return metin.strip(" -\r\n")

def alt_sayfa_metnini_cek(link):
    """Alt sayfadaki tam metni YZ bağlamını bozmayacak şekilde saf metin olarak çeker"""
    if link.endswith('.pdf'):
        return "[PDF_DOSYASI: Bu içerik doğrudan PDF formatındadır, metin analizi için harici katman gerekir.]"
        
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(link, headers=headers, verify=False, timeout=20)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding if r.apparent_encoding else 'windows-1254'
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Sayfa içindeki gereksiz script, stil, menü ve footer'ları at
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
                
            # Resmi Gazete metin gövdesini hedefle
            Hedef_alanlar = soup.find_all(['p', 'div'], class_=['özet', 'metin', 'İçerik', 'icerik'])
            if hedef_alanlar:
                metinler = [metin_temizle(p.get_text()) for p in hedef_alanlar]
                return " ".join([m for m in metinler if len(m) > 10])
            else:
                # Fallback: Tüm body metnini temiz al
                body = soup.find('body')
                if body:
                    return metin_temizle(body.get_text())
    except Exception as e:
        print(f"[UYARI] Alt sayfa okunamadı ({link}): {str(e)}")
    return ""

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

def git_commit_push(dosya_yolu):
    try:
        subprocess.run(["git", "config", "--global", "user.name", "Bozkurt Bot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@bozkurt.local"], check=True)
        subprocess.run(["git", "add", dosya_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Otonom: Cevrimdisi veri kuyruga eklendi"], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print(f"[HATA] Git yedekleme başarısız: {str(e)}")

def git_sil_push(dosya_yolu):
    try:
        if os.path.exists(dosya_yolu):
            os.remove(dosya_yolu)
        subprocess.run(["git", "add", dosya_yolu], check=True)
        subprocess.run(["git", "commit", "-m", "Otonom: Basariyla gonderilen kuyruk temizlendi"], check=True)
        subprocess.run(["git", "push"], check=True)
    except:
        pass

def veri_gonder(payload, dosya_yolu=None):
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url: return False
    try:
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[BAŞARILI] {payload['tarih']} LLM-Ready verileri Ana PC'ye mühürlendi.")
            if dosya_yolu and os.path.exists(dosya_yolu):
                git_sil_push(dosya_yolu)
            return True
    except:
        print(f"[UYARI] Ana PC'ye ulaşılamadı, kuyruğa alınıyor...")
        
    if dosya_yolu is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_yolu = os.path.join(KUYRUK_KLASORU, f"kuyruk_{payload['tarih']}_{timestamp}.json")
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        git_commit_push(dosya_yolu)
    return False

def kuyrugu_isle():
    dosyalar = glob.glob(os.path.join(KUYRUK_KLASORU, "*.json"))
    for dosya in dosyalar:
        with open(dosya, "r", encoding="utf-8") as f:
            payload = json.load(f)
        veri_gonder(payload, dosya_yolu=dosya)

def gunu_kazi(tarih_obj, deneme_sayisi=1):
    tarih_str = tarih_obj.strftime("%Y%m%d")
    yil = tarih_obj.strftime("%Y")
    ay = tarih_obj.strftime("%m")
    
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        if response.status_code != 200:
            return True 
            
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'windows-1254'
        soup = BeautifulSoup(response.text, 'html.parser')
        veriler = []
        
        # Bölümleri ve başlıkları hiyerarşik yakala
        mevcut_kategori = "GENEL"
        
        for element in soup.find_all(['h2', 'h3', 'h4', 'a'], href=True):
            tag_name = element.name
            text = metin_temizle(element.get_text())
            
            if tag_name in ['h2', 'h3', 'h4'] and len(text) > 3:
                mevcut_kategori = text
                continue
                
            if text and len(text) > 5:
                link = urljoin("https://www.resmigazete.gov.tr", element['href'])
                
                # Sadece geçerli Resmi Gazete alt sayfalarını işle
                if "resmigazete.gov.tr" in link:
                    print(f"[KAZIMA] ({mevcut_kategori}) -> {text[:40]}...")
                    tam_metin = alt_sayfa_metnini_cek(link)
                    
                    veriler.append({
                        "kategori": mevcut_kategori,
                        "baslik": text,
                        "link": link,
                        "tam_metin": tam_metin
                    })
                    time.sleep(0.5) # Sunucu koruması
                
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
            time.sleep(15 * deneme_sayisi)
            return gunu_kazi(tarih_obj, deneme_sayisi + 1)
        return False
    except Exception as e:
        print(f"[HATA] {tarih_str} işlenirken hata: {str(e)}")
        return False

def kazima_islem():
    baslangic_zamani = time.time()
    MAX_SURE = 4.5 * 3600 
    
    kuyrugu_isle() 
    
    bugun = datetime.now()
    gunu_kazi(bugun)
    
    en_eski_tarih_str = get_arsiv_durumu()
    if not en_eski_tarih_str:
        en_eski_tarih_str = bugun.strftime("%Y-%m-%d")
        
    hedef_tarih = datetime.strptime(en_eski_tarih_str, "%Y-%m-%d") - timedelta(days=1)
    
    while True:
        if (time.time() - baslangic_zamani) >= MAX_SURE:
            break
        if hedef_tarih.strftime("%Y-%m-%d") <= "1921-02-07":
            break
            
        gunu_kazi(hedef_tarih)
        time.sleep(random.uniform(2.0, 4.0))
        hedef_tarih -= timedelta(days=1)

if __name__ == "__main__":
    kazima_islem()
