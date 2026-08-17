import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

def kazima_baslat():
    # Resmi Gazete Ana Sayfası (Sadece bağlantı testi için)
    url = "https://www.resmigazete.gov.tr/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"[BİLGİ] {url} adresine bağlanılıyor...")
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    
    if response.status_code != 200:
        print(f"[HATA] Sayfaya ulaşılamadı. Durum Kodu: {response.status_code}")
        return
        
    soup = BeautifulSoup(response.text, 'html.parser')
    veriler = []
    
    for link in soup.find_all('a', href=True):
        text = link.get_text(strip=True)
        if text and len(text) > 5:
            hedef_link = url + link['href'] if link['href'].startswith('/') else link['href']
            veriler.append({"baslik": text, "link": hedef_link})
            
    # Bozkurt Core'a fırlatılacak test paketi
    payload = {
        "source": "resmi_gazete_test",
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "toplanan_icerik_sayisi": len(veriler),
        "veriler": veriler
    }
    
    # GitHub Secrets'tan API adresimizi çekiyoruz
    api_url = os.environ.get("BOZKURT_API_URL")
    
    if not api_url:
        print("[HATA] BOZKURT_API_URL bulunamadı!")
        return
        
    print(f"[BİLGİ] Veriler Ana PC'ye fırlatılıyor...")
    
    try:
        api_response = requests.post(api_url, json=payload, timeout=15)
        if api_response.status_code == 200:
            print("[BAŞARILI] Bağlantı Kuruldu! Veriler Ubuntu'ya ulaştı.")
        else:
            print(f"[HATA] Fırlatma başarısız. Durum Kodu: {api_response.status_code}")
    except Exception as e:
        print(f"[HATA] Bozkurt Core'a ulaşılamadı: {str(e)}")

if __name__ == "__main__":
    kazima_baslat()
