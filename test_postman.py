import requests

base_url = "http://127.0.0.1:5000"

print("1. Login")
res = requests.post(f"{base_url}/login", data={"kullanici_adi": "admin", "sifre": "yanlis_sifre_testi"})
print("Status:", res.status_code)

print("2. Takvim")
res = requests.get(f"{base_url}/api/takvim")
print("Status:", res.status_code)

print("3. Musaitlik")
res = requests.get(f"{base_url}/api/musaitlik-kontrol?personel_id=1&tarih=2026-07-20")
print("Status:", res.status_code)

print("4. XSS")
res = requests.post(f"{base_url}/", data={"ad_soyad": "Hacker <script>alert(1)</script>", "tc_kimlik": "11111111110"})
print("Status:", res.status_code)
