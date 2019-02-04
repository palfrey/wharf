from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import os
from subprocess import Popen, PIPE, STDOUT, run, check_call, check_output, CalledProcessError
import io
import uuid

chrome_options = webdriver.ChromeOptions()
chrome_options.headless = True
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
driver = webdriver.Chrome(os.environ["CHROMEDRIVER_PATH"], chrome_options=chrome_options, service_args=['--verbose'])
driver.implicitly_wait(0)

def find_element_by_id(id):
    def find(driver):
        elements = driver.find_elements_by_id(id)
        if len(elements) == 1:
            return elements[0]
        elif len(elements) == 0:
            return None
        else:
            raise Exception(elements)
    return find

def wait_for_one(driver, locators):
    for locator in locators:
        element = locator(driver)
        if element != None:
            return element
    return False

def get_main_id():
    res = WebDriverWait(driver, 10).until(
        lambda driver: wait_for_one(driver, [find_element_by_id("initial-setup-header"), find_element_by_id("list_apps")])
    )
    return res.get_attribute("id")

try:
    driver.get(sys.argv[1])
    driver.find_element_by_name("username").send_keys("admin")
    driver.find_element_by_name("password").send_keys("password")
    driver.find_element_by_name("submit").click()
    id = get_main_id()
    if id == "list_apps":
        print("Checking SSH status")
        driver.find_element_by_id("refresh_info").click()
        id = get_main_id() # because keys might not work any more
    if id == "initial-setup-header":
        print("Adding new keys")
        keys = check_output("sudo dokku ssh-keys:list".split(" ")).decode("utf-8")
        if "check_boot" in keys:
            check_call("sudo dokku ssh-keys:remove check_boot".split(" "))
        element = driver.find_element_by_id("ssh-key")
        cmd = "echo " + element.text + " | sudo dokku ssh-keys:add check_boot"
        print(cmd)
        ret = os.system(cmd)
        assert ret == 0
        driver.get(sys.argv[1])
    elif id == "list_apps":
        pass
    else:
        raise Exception(id)
    app_name = uuid.uuid4().hex
    print("Making new app " + app_name)
    driver.find_element_by_id("id_name").send_keys(app_name)
    driver.find_element_by_id("create_app").click()
    WebDriverWait(driver, 10).until(
        lambda driver: wait_for_one(driver, [find_element_by_id("app_page")])
    )
    assert driver.page_source.find(app_name) != -1
except:
    driver.get_screenshot_as_file('where.png')
    raise
finally:
    driver.quit()