import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

os.makedirs('/tmp/screenshots', exist_ok=True)

print("Starting webdriver...")
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1280,800")
driver = webdriver.Chrome(options=chrome_options)

base_url = "http://127.0.0.1:5001"

try:
    print("1. Login Page")
    driver.get(f"{base_url}/login")
    time.sleep(2)
    driver.save_screenshot('/tmp/screenshots/1_login.png')
    
    print("Logging in...")
    driver.find_element(By.ID, "kullanici_adi").send_keys("admin")
    driver.find_element(By.ID, "sifre").send_keys("admin123")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(2)
    
    print("2. Dashboard")
    driver.get(f"{base_url}/dashboard")
    time.sleep(2)
    driver.save_screenshot('/tmp/screenshots/2_dashboard.png')
    
    print("3. Yeni Randevu")
    driver.get(f"{base_url}/yeni-randevu")
    time.sleep(2)
    driver.save_screenshot('/tmp/screenshots/3_randevu.png')
    
    print("4. Ziyaretciler")
    driver.get(f"{base_url}/ziyaretciler")
    time.sleep(2)
    driver.save_screenshot('/tmp/screenshots/4_ziyaretciler.png')
    
    print("5. Personel Yonetimi")
    driver.get(f"{base_url}/personel-yonetimi")
    time.sleep(2)
    driver.save_screenshot('/tmp/screenshots/5_personel.png')

    print("Done!")
finally:
    driver.quit()
