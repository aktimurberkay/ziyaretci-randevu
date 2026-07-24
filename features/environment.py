from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def before_all(context):
    print("--- TEST BASLIYOR ---")
    options = webdriver.ChromeOptions()
    options.add_argument('--window-size=1280,800')
    context.driver = webdriver.Chrome(options=options)
    context.driver.implicitly_wait(10)

def after_step(context, step):
    time.sleep(1)

def after_all(context):
    time.sleep(2)
    print("--- TEST BITTI ---")
    context.driver.quit()
