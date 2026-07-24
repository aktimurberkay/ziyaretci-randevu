from selenium.webdriver.common.by import By

class AdminPage:
    def __init__(self, driver):
        self.driver = driver

    def set_username(self, username):
        self.driver.find_element(By.ID, "kullanici_adi").send_keys(username)

    def set_password(self, password):
        self.driver.find_element(By.ID, "sifre").send_keys(password)

    def submit_login(self):
        self.driver.find_element(By.XPATH, "//button[@type='submit']").click()

    def click_onayla(self, isim):
        xpath = f"//tr[td[contains(., '{isim}')]]//button[contains(., 'Onayla')]"
        btn = self.driver.find_element(By.XPATH, xpath)
        btn.submit()

    def click_duzenle(self, isim):
        xpath = f"//tr[td[contains(., '{isim}')]]//button[contains(@onclick, 'showDuzenleModal')]"
        btn = self.driver.find_element(By.XPATH, xpath)
        self.driver.execute_script("arguments[0].click();", btn)

    def set_duzenle_notlar(self, payload):
        textarea = self.driver.find_element(By.ID, "duzenle_notlar")
        textarea.clear()
        textarea.send_keys(payload)

    def submit_duzenle(self):
        btn = self.driver.find_element(By.XPATH, "//form[@id='duzenleForm']//button[@type='submit']")
        self.driver.execute_script("arguments[0].click();", btn)

    def verify_no_alert(self):
        try:
            alert = self.driver.switch_to.alert
            if "özel karakterler" in alert.text or "Bu alana" in alert.text:
                alert.accept()
                return True # XSS Korumasi Calisti (Uygulama uyarisi)
            elif "XSS" in alert.text:
                return False # XSS Payload Calisti (Zafiyet)
            else:
                alert.accept()
                return False # Beklenmeyen alert
        except:
            return True # Alert yok, sayfa reload oldu ve payload calismadi (Guvenli)
