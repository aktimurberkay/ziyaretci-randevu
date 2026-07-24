import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1280,800")
driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("http://127.0.0.1:5001/")
    time.sleep(2)
    driver.save_screenshot('/Users/berkayaktimur/.gemini/antigravity/brain/659aa6d3-4671-4ccb-b127-ca16a290bcdd/form_screenshot.png')
    print("Screenshot saved.")
finally:
    driver.quit()
