from locust import HttpUser, task, between
import json

class ZiyaretciAppUser(HttpUser):
    wait_time = between(1, 5) # Kullanıcı işlemleri arasında 1 ile 5 saniye bekler

    def on_start(self):
        # Her simüle edilen kullanıcı başladığında giriş yapar
        response = self.client.post("/login", data={
            "kullanici_adi": "admin",
            "sifre": "admin"
        })
        if response.status_code == 200 or response.status_code == 302:
            print("Locust Kullanıcısı Giriş Yaptı")

    @task(3)
    def index_page(self):
        # Kullanıcıların çoğu ana sayfayı ziyaret eder
        self.client.get("/")

    @task(2)
    def dashboard_page(self):
        # Admin paneline giriş
        self.client.get("/dashboard")

    @task(1)
    def view_personel(self):
        # API'den müsaitlik kontrolü simülasyonu
        self.client.get("/api/musaitlik-kontrol?personel_id=1&tarih_saat=2026-08-01T10:00")
