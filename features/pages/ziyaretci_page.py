from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

class ZiyaretciPage:
    def __init__(self, driver):
        self.driver = driver

    def set_ad_soyad(self, ad_soyad):
        self.driver.find_element(By.NAME, "ad_soyad").send_keys(ad_soyad)

    def set_tc_kimlik(self, tc):
        self.driver.find_element(By.NAME, "tc_kimlik").send_keys(tc)

    def set_eposta(self, email):
        self.driver.find_element(By.NAME, "eposta").send_keys(email)

    def select_personel(self, index=1):
        select = Select(self.driver.find_element(By.ID, "personel_select"))
        select.select_by_index(index)

    def set_tarih_natively(self, date_str):
        tarih_input = self.driver.find_element(By.ID, "randevu_tarihi")
        tarih_input.send_keys(date_str)
        self.driver.execute_script("loadMusaitSaatler();")

    def select_saat(self, index=1):
        select = Select(self.driver.find_element(By.ID, "randevu_saati"))
        select.select_by_index(index)

    def set_notlar(self, notlar):
        self.driver.find_element(By.NAME, "notlar").send_keys(notlar)

    def check_kvkk(self):
        kvkk = self.driver.find_element(By.NAME, "kvkk_onayi")
        if not kvkk.is_selected():
            self.driver.execute_script("arguments[0].click();", kvkk)

    def submit_form(self):
        btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
        btn.submit()

    def verify_success_message(self):
        msg = self.driver.find_element(By.XPATH, "//div[contains(@class, 'alert-success') or contains(text(), 'başarı')]")
        return msg.is_displayed()
