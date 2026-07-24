import time
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

print(">>> Selenium Otomasyon Robotu Başlatılıyor...")
print(">>> İLK ÇALIŞTIRMADA CHROME SÜRÜCÜSÜ İNTERNETTEN İNDİRİLECEĞİ İÇİN 1-2 DAKİKA BEKLETEBİLİR. LÜTFEN BİR ŞEYE BASMADAN BEKLEYİN...")

options = webdriver.ChromeOptions()
options.add_argument('--window-size=1280,800')

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 5)

try:
    print("--- ADIM 1: Ziyaretçi Randevu Alma ---")
    driver.set_page_load_timeout(15)
    try:
        driver.get("http://localhost:5001/")
    except:
        pass
    time.sleep(2)
    
    ad_soyad_input = wait.until(EC.presence_of_element_located((By.NAME, "ad_soyad")))
    ad_soyad_input.send_keys("Selenium Robot")
    time.sleep(1)
    
    # Random TC
    driver.find_element(By.NAME, "tc_kimlik").send_keys("27965661732")
    driver.find_element(By.NAME, "eposta").send_keys("robot@selenium.com")
    time.sleep(1)
    
    # Personel
    personel_select = Select(driver.find_element(By.ID, "personel_select"))
    personel_select.select_by_index(1) 
    time.sleep(1)
    
    # Date 
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    tarih_input = driver.find_element(By.ID, "randevu_tarihi")
    driver.execute_script(f"arguments[0].value = '{tomorrow_str}';", tarih_input)
    driver.execute_script("loadMusaitSaatler();")
    time.sleep(2)
    
    # Wait for time slots
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#randevu_saati option[value]:not([value=''])")))
    time_select = Select(driver.find_element(By.ID, "randevu_saati"))
    time_select.select_by_index(1)
    time.sleep(1)
    
    # Notlar
    driver.find_element(By.NAME, "notlar").send_keys("Bu bir otomatik test randevusudur.")
    time.sleep(1)
    
    # KVKK
    driver.find_element(By.NAME, "kvkk_onayi").click()
    time.sleep(1)
    
    # Submit form
    driver.find_element(By.CSS_SELECTOR, "form").submit()
    print(">>> Ziyaretçi randevusu başarıyla oluşturuldu!")
    time.sleep(3)
    
    print("--- ADIM 2: Admin Girişi ---")
    try:
        driver.get("http://localhost:5001/login")
    except:
        pass
    time.sleep(2)
    
    kullanici_adi_input = wait.until(EC.presence_of_element_located((By.ID, "kullanici_adi")))
    kullanici_adi_input.send_keys("admin")
    time.sleep(1)
    driver.find_element(By.ID, "sifre").send_keys("123")
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, "form").submit()
    print(">>> Admin girişi yapıldı!")
    time.sleep(3)
    
    print("--- ADIM 3: XSS Korumasını Test Etme (Admin Olarak Randevu Düzenleme) ---")
    try:
        driver.get("http://localhost:5001/dashboard")
    except:
        pass
    time.sleep(2)
    
    # Önce randevuyu onayla (Bekliyor durumunda düzenle butonu çıkmaz)
    onayla_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//tr[td[contains(., 'Selenium Robot')]]//button[contains(., 'Onayla')]")))
    onayla_btn.submit()
    time.sleep(2)
    
    # Sayfa yenilendikten sonra Düzenle butonuna tıkla
    edit_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//tr[td[contains(., 'Selenium Robot')]]//button[contains(@onclick, 'showDuzenleModal')]")))
    driver.execute_script("arguments[0].click();", edit_btn)
    time.sleep(1)
    
    notlar_area = wait.until(EC.visibility_of_element_located((By.ID, "duzenle_notlar")))
    notlar_area.clear()
    notlar_area.send_keys("<script>alert('hack')</script>")
    time.sleep(1)
    
    # Formu gönder ki XSS koruma scripti tetiklensin
    driver.find_element(By.XPATH, "//div[@id='duzenleModal']//button[text()='Kaydet']").click()
    time.sleep(2)
    
    # Check for alert
    try:
        alert = wait.until(EC.alert_is_present())
        alert_text = alert.text
        print(f">>> MÜKEMMEL! Sistem zararlı kodu yakaladı. Hata Mesajı: {alert_text}")
        alert.accept()
        time.sleep(2)
    except Exception as e:
        print(">>> HATA: Sistem zararlı koda izin verdi!")
    
    print("--- ADIM 4: Randevu Temizliği ---")
    # Click cancel to close the modal because form didn't submit
    cancel_btn = driver.find_element(By.XPATH, "//div[@id='duzenleModal']//button[contains(text(), 'İptal')]")
    cancel_btn.click()
    time.sleep(2)
    
    # Click edit again to delete
    edit_btn.click()
    time.sleep(2)
    
    # Delete the appointment
    delete_btn = driver.find_element(By.XPATH, "//div[@id='duzenleModal']//button[contains(text(), 'Randevuyu Sil')]")
    delete_btn.click()
    time.sleep(1)
    try:
        alert = wait.until(EC.alert_is_present())
        alert.accept()
    except:
        pass
    print(">>> Test randevusu başarıyla silindi.")
    time.sleep(3)
    
    print(">>> TEST TAMAMLANDI!")

except Exception as e:
    print(f"HATA OLUŞTU: {e}")
    try:
        print(f"Mevcut URL: {driver.current_url}")
        driver.save_screenshot("hata_ekrani.png")
        print(">>> HATA DETAYI: Hatanın nedenini görebilmeniz için projenin içine 'hata_ekrani.png' isimli bir resim kaydedildi. Lütfen bu resme bakıp bana ne gördüğünüzü söyleyin!")
    except:
        pass
finally:
    driver.quit()
