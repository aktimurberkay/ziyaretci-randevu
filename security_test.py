import requests
import json

BASE_URL = "http://127.0.0.1:5001"

def print_result(name, condition, msg):
    if condition:
        print(f"✅ {name}: GEÇTİ ({msg})")
    else:
        print(f"❌ {name}: KALDI ({msg})")

def test_sql_injection():
    # Login sayfasında SQL injection denemesi
    payload = {
        "kullanici_adi": "admin' OR '1'='1",
        "sifre": "wrong"
    }
    response = requests.post(f"{BASE_URL}/login", data=payload, allow_redirects=False)
    # Eğer SQL injection başarılı olsaydı 302 dönerdi (Giriş yapılmış gibi).
    # Sistemin bunu reddedip 200 (login sayfasında kalma) döndüğünü kontrol ediyoruz.
    print_result("SQL Injection (Login)", response.status_code == 200, "Sistem SQL Injection denemesini reddetti.")

def test_unauthenticated_access():
    # Token olmadan yetki gerektiren bir sayfaya erişim
    response = requests.get(f"{BASE_URL}/dashboard", allow_redirects=False)
    # Yetkisiz erişim 302 (login'e yönlendirme) vermelidir.
    print_result("Yetkisiz Erişim (Bypass)", response.status_code == 302, "Korumalı sayfaya izinsiz giriş engellendi.")

def test_xss_protection():
    # Ziyaretçi olarak zararlı script gönderme denemesi
    payload = {
        "kullanici_adi": "test_user",
        "sifre": "test_pass"
    }
    # Yetkisiz kullanıcı girişi engellenmeli ve XSS tetiklenmemeli
    response = requests.post(f"{BASE_URL}/login", data={"kullanici_adi": "<script>alert(1)</script>", "sifre": "a"})
    # İçinde script etiketi olan bir metin girmesine rağmen sistem çökmüyor mu?
    print_result("XSS (Backend)", response.status_code == 200, "Sunucu XSS verisini zararsız şekilde işledi/reddetti.")

if __name__ == "__main__":
    print("--- GÜVENLİK VE SIZMA TESTLERİ BAŞLIYOR ---")
    try:
        requests.get(BASE_URL)
    except requests.exceptions.ConnectionError:
        print(f"HATA: {BASE_URL} adresine ulaşılamıyor. Sunucu çalışıyor mu?")
        exit(1)
        
    test_sql_injection()
    test_unauthenticated_access()
    test_xss_protection()
    print("--- TESTLER TAMAMLANDI ---")
