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
import PyPDF2  # PDF'leri GitHub üzerinde okumak için
from urllib.parse import urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KUYRUK_KLASORU = "kuyruk"
os.makedirs(KUYRUK_KLASORU, exist_ok=True)

# --- METİN VE PDF İŞLEME FONKSİYONLARI ---

def metin_temizle(metin):
    """Gereksiz boşlukları ve HTML/PDF artıklarını temizler."""
    if not metin:
        return ""
    metin = re.sub(r'\s+', ' ', metin)
    return metin.strip(" -\r\n")

def pdf_metnini_cek(pdf_icerik):
    """GitHub'ın belleğine inen PDF dosyasının içindeki metinleri çıkarır."""
    try:
        with io.BytesIO(pdf_icerik) as f:
            pdf = PyPDF2.PdfReader(f)
            metin = ""
            for sayfa in pdf.pages:
                cekilen = sayfa.extract_text()
                if cekilen:
                    metin += cekilen + " "
            return metin_temizle(metin)
    except Exception as e:
        return f"[PDF_OKUMA_HATASI: İçerik şifreli veya metin dışı formatta olabilir]"

def alt_sayfa_metnini_cek(link):
    """Linkteki içeriğin PDF mi yoksa HTML mi olduğunu anlar ve temiz metni döner."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(link, headers=headers, verify=False, timeout=25)
        if r.status_code == 200:
            
            # 1. Kontrol: Sayfa PDF mi?
            content_type = r.headers.get('Content-Type', '').lower()
            if 'application/pdf' in content_type or link.lower().endswith('.pdf'):
                return pdf_metnini_cek(r.content)
            
            # 2. Kontrol: Sayfa normal HTML ise
            r.encoding = r.apparent_encoding if r.apparent_encoding else 'windows-1254'
            soup = BeautifulSoup(r.text, 'html.parser')
            
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
                
            hedef_alanlar = soup.find_all(['p', 'div'], class_=['özet', 'metin', 'İçerik', 'icerik'])
            if hedef_alanlar:
                metinler = [metin_temizle(p.get_text()) for p in hedef_alanlar]
                return " ".join([m for m in metinler if len(m) > 10])
            else:
                body = soup.find('body')
                if body:
                    return metin_temizle(body.get_text())
    except Exception as e:
        pass
    return ""

# --- HABERLEŞME VE VERİ GÖNDERİMİ ---

def get_arsiv_durumu():
    """Ubuntu'dan en eski tarihi sorar."""
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
    """GitHub deposuna yedekleme yapar veya siler."""
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
    """Süzülmüş saf metni JSON olarak Ubuntu Ana PC'ye fırlatır."""
    api_url = os.environ.get("BOZKURT_API_URL")
    if not api_url: return False
    
    try:
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code == 200:
            print(f"[BAŞARILI] {payload['tarih']} verileri (PDF & HTML) Ubuntu'ya mühürlendi.")
            if dosya_yolu:
                git_islem(dosya_yolu, "sil")
            return True
    except:
        print(f"[UYARI] Ubuntu'ya ulaşılamadı, veri GitHub kuyruğuna alınıyor...")
        
    if dosya_yolu is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_yolu = os.path.join(KUYRUK_KLASORU, f"kuyruk_{payload['tarih']}_{timestamp}.json")
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        git_islem(dosya_yolu, "ekle")
    return False

# --- ANA KAZIMA DÖNGÜSÜ (5 Saatlik Geriye Tarama) ---

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
        mevcut_kategori = "GENEL"
        
        for element in soup.find_all(['h2', 'h3', 'h4', 'a'], href=True):
            tag_name = element.name
            text = metin_temizle(element.get_text())
            
            if tag_name in ['h2', 'h3', 'h4'] and len(text) > 3:
                mevcut_kategori = text
                continue
                
            if text and len(text) > 5:
                link = urljoin("https://www.resmigazete.gov.tr", element['href'])
                
                if "resmigazete.gov.tr" in link:
                    print(f"[KAZIMA] İşleniyor: {text[:40]}...")
                    tam_metin = alt_sayfa_metnini_cek(link)
                    
                    veriler.append({
                        "kategori": mevcut_kategori,
                        "baslik": text,
                        "link": link,
                        "tam_metin": tam_metin
                    })
                    time.sleep(0.5) # GitHub çok hızlıdır, siteyi yormayalım
                
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
    baslangic_zamani = time.time()
    MAX_SURE = 4.5 * 3600 # 4.5 Saatlik güvenlik sınırı
    
    # Varsa önceki günlerden kalan kuyruğu erit
    dosyalar = glob.glob(os.path.join(KUYRUK_KLASORU, "*.json"))
    for dosya in dosyalar:
        with open(dosya, "r", encoding="utf-8") as f:
            veri_gonder(json.load(f), dosya_yolu=dosya)
            
    bugun = datetime.now()
    gunu_kazi(bugun)
    
    en_eski_tarih_str = get_arsiv_durumu()
    if not en_eski_tarih_str:
        en_eski_tarih_str = bugun.strftime("%Y-%m-%d")
        
    hedef_tarih = datetime.strptime(en_eski_tarih_str, "%Y-%m-%d") - timedelta(days=1)
    
    while True:
        if (time.time() - baslangic_zamani) >= MAX_SURE:
            print("[BİLGİ] GitHub maksimum çalışma süresine yaklaştı. Görev güvenle devrediliyor.")
            break
        if hedef_tarih.strftime("%Y-%m-%d") <= "1921-02-07":
            print("[BİLGİ] Bütün arşiv tarandı.")
            break
            
        gunu_kazi(hedef_tarih)
        time.sleep(random.uniform(2.0, 4.0)) # Ban yememek için rastgele mola
        hedef_tarih -= timedelta(days=1)

if __name__ == "__main__":
    kazima_islem()
