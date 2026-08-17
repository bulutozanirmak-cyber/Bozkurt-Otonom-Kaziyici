import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import urllib3

# SSL sertifika doğrulama uyarılarını kapatıyoruz
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def kazima_islem():
    # Bugünün tarihini alıyoruz (Geçmişe dönük döngü için baz tarih)
    bugun = datetime.now()
    
    # Şimdilik en son yayımlanan Resmi Gazete'yi hedefliyoruz
    tarih_str = bugun.strftime("%Y%m%d")
    yil = bugun.strftime("%Y")
    ay = bugun.strftime("%m")
    
    # Resmi Gazete Arşiv URL Yapısı
    url = f"https://www.resmigazete.gov.tr/eskiler/{yil}/{ay}/{tarih_str}.htm"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[BİLGİ] {url} adresinden veriler çekiliyor...")
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        
        # Eğer bugün henüz Resmi Gazete yayımlanmadıysa bir önceki güne bakabilir
        if response.status_code != 200:
            print(f"[UYARI] {tarih_str} tarihli Resmi Gazete henüz bulunamadı. Kod: {response.status_code}")
            return

        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        veriler = []
        # Sayfadaki başlıkları ve ilgili alt bağlantıları topluyoruz
        for item in soup.find_all(['h2', 'h3', 'a'], href=True):
            text = item.get_text(strip=True)
            if text and len(text) > 5:
                link = item['href']
                if not link.startswith('http'):
                    link = f"https://www.resmigazete.gov.tr{link}"
                veriler.append({
                    "baslik": text,
                    "link": link
                })
                
        payload = {
            "source": "resmi_gazete_gercek",
            "tarih": bugun.strftime("%Y-%m-%d"),
            "toplanan_icerik_sayisi": len(veriler),
            "veriler": veriler
        }
        
        api_url = os.environ.get("BOZKURT_API_URL")
        if not api_url:
            print("[HATA] BOZKURT_API_URL tanımlı değil!")
            return
            
        print(f"[BİLGİ] Toplanan {len(veriler)} içerik Ana PC'ye fırlatılıyor...")
        
        api_response = requests.post(api_url, json=payload, timeout=30)
        if api_response.status_code == 200:
            print("[BAŞARILI] Resmi Gazete verileri Ana PC'ye mühürlendi.")
        else:
            print(f"[HATA] Fırlatma başarısız. Durum Kodu: {api_response.status_code}")
            
    except Exception as e:
        print(f"[KRİTİK HATA] Kazıma sırasında hata oluştu: {str(e)}")

if __name__ == "__main__":
    kazima_islem()
