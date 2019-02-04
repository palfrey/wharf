from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import os

chrome_options = webdriver.ChromeOptions()
chrome_options.headless = True
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
driver = webdriver.Chrome(os.environ["CHROMEDRIVER_PATH"], chrome_options=chrome_options, service_args=['--verbose'])
try:
    driver.get(sys.argv[1])
    driver.find_element_by_name("username").send_keys("admin")
    driver.find_element_by_name("password").send_keys("password")
    driver.find_element_by_name("submit").click()
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "initial-setup-header"))
    )
finally:
    driver.quit()