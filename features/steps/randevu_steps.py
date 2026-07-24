from behave import given, when, then
from pages.ziyaretci_page import ZiyaretciPage
from pages.admin_page import AdminPage
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import datetime
import time

# Ziyaretci Adimlari
@given('Ziyaretci randevu olusturma anasayfasindadir')
def step_impl(context):
    context.driver.get("http://127.0.0.1:5001/")
    context.ziyaretci = ZiyaretciPage(context.driver)

@when('Ad Soyad alanina "{isim}" girilirse')
def step_impl(context, isim):
    context.ziyaretci.set_ad_soyad(isim)

@when('TC Kimlik alanina gecerli bir "{tc}" degeri girilirse')
def step_impl(context, tc):
    context.ziyaretci.set_tc_kimlik(tc)

@when('E-posta alanina "{email}" girilirse')
def step_impl(context, email):
    context.ziyaretci.set_eposta(email)

@when('Gorusulecek Kisi secim alanindan ilk personel secilirse')
def step_impl(context):
    context.ziyaretci.select_personel(1)

@when('Randevu Tarihi olarak yarin secilirse')
def step_impl(context):
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%d%m%Y")
    context.ziyaretci.set_tarih_natively(tomorrow_str)

@when('Randevu Saati olarak uygun bir saat secilirse')
def step_impl(context):
    wait = WebDriverWait(context.driver, 5)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#randevu_saati option[value]:not([value=''])")))
    context.ziyaretci.select_saat(1)

@when('Notlar alanina "{notlar}" girilirse')
def step_impl(context, notlar):
    context.ziyaretci.set_notlar(notlar)

@when('KVKK onay kutusu isaretlenirse')
def step_impl(context):
    context.ziyaretci.check_kvkk()

@when('Randevu formunda Gonder butonuna tiklanirsa')
def step_impl(context):
    context.ziyaretci.submit_form()
    time.sleep(2)

@then('Randevunun basariyla olusturuldugu mesajinin goruntulendigi dogrulanmalidir')
def step_impl(context):
    assert context.ziyaretci.verify_success_message() is True


# Admin Adimlari
@given('Admin login sayfasindadir')
def step_impl(context):
    context.driver.get("http://127.0.0.1:5001/login")
    context.admin = AdminPage(context.driver)

@when('Kullanici adi alanina "{username}" degeri girilirse')
def step_impl(context, username):
    context.admin.set_username(username)

@when('Sifre alanina "{password}" degeri girilirse')
def step_impl(context, password):
    context.admin.set_password(password)

@when('Login formunda Giris butonuna tiklanirsa')
def step_impl(context):
    context.admin.submit_login()
    time.sleep(2)

@then('Admin panelinin acildigi goruntulenmelidir')
def step_impl(context):
    assert "Hoş Geldiniz" in context.driver.page_source

@when('Dashboard uzerinde bekleyen "{isim}" adli randevunun Onayla butonuna tiklanirsa')
def step_impl(context, isim):
    context.admin.click_onayla(isim)
    time.sleep(2)

@then('Randevu durumunun onaylandi olarak degistigi goruntulenmelidir')
def step_impl(context):
    assert "Randevu durumu güncellendi: Onaylandı" in context.driver.page_source

@when('"{isim}" adli randevunun Duzenle butonuna tiklanirsa')
def step_impl(context, isim):
    context.admin.click_duzenle(isim)
    time.sleep(1)

@then('Randevu Duzenleme modalinin acildigi goruntulenmelidir')
def step_impl(context):
    assert "Randevu Düzenle" in context.driver.page_source

@then('Duzenle Notlar alanina "{payload}" degeri girilirse')
def step_impl(context, payload):
    context.admin.set_duzenle_notlar("<script>alert('XSS Başarılı')</script>")

@then('Duzenleme modalinda Kaydet butonuna tiklanirsa')
def step_impl(context):
    context.admin.submit_duzenle()
    time.sleep(2)

@then('Sistem xss korumasinin devrede oldugu ve zafiyet barindirmadigi dogrulanmalidir')
def step_impl(context):
    assert context.admin.verify_no_alert() is True
