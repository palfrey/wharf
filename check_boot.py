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
import time

class Tester:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.headless = True
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--start-maximized')
        chromium_browser = os.environ.get("CHROMIUM_BROWSER", None)
        if chromium_browser != None:
            chrome_options.binary_location = chromium_browser
        self.driver = webdriver.Chrome(os.environ["CHROMEDRIVER_PATH"], chrome_options=chrome_options, service_args=['--verbose'])
        self.driver.implicitly_wait(0)
        self.start = time.time()

    def log(self, message):
        print("%f: %s" % (time.time()-self.start, message))

    def find_one(self, elements):
        if len(elements) == 1:
            return elements[0]
        elif len(elements) == 0:
            return None
        else:
            raise Exception(elements)

    def find_element(self, strat, id, allow_none=False):
        self.log("Looking for %s: '%s'" % (strat, id))
        ret = self.find_one(self.driver.find_elements(strat, id))
        if ret == None and not allow_none:
            self.failure()
            raise Exception("No such element with %s and %s" % (strat, id))
        return ret

    def wait_for_one(self, locators):
        for locator in locators:
            element = self.find_element(*locator, allow_none=True)
            if element != None:
                return element
        return False

    def failure(self):
        self.driver.get_screenshot_as_file("screenshot.png")

    def get(self, url):
        self.log("Went to %s" % url)
        return self.driver.get(url)

    def send_keys(self, strat, id, text):
        self.log("Send keys '%s' to %s: '%s'" % (text, strat, id))
        return self.find_element(strat, id).send_keys(text)
    
    def click(self, strat, id):
        self.log("Click on %s: '%s'" %(strat, id))
        return self.find_element(strat, id).click()

    def wait_for_list(self, items):
        return WebDriverWait(self.driver, 10).until(
            lambda driver: self.wait_for_one(items)
        )

    def get_main_id(self):
        res = self.wait_for_list([(By.ID, "initial-setup-header"), (By.ID, "list_apps")])
        return res.get_attribute("id")
    
    def page_source(self):
        return self.driver.page_source

try:
    tester = Tester()
    tester.get(sys.argv[1])
    tester.send_keys(By.NAME, "username", "admin")
    tester.send_keys(By.NAME, "password", "password")
    tester.click(By.NAME, "submit")
    id = tester.get_main_id()
    if id == "list_apps":
        tester.log("Checking SSH status")
        tester.click(By.ID, "refresh_info")
        id = tester.get_main_id() # because keys might not work any more
    if id == "initial-setup-header":
        tester.log("Adding new keys")
        keys = check_output("sudo dokku ssh-keys:list".split(" ")).decode("utf-8")
        if "check_boot" in keys:
            check_call("sudo dokku ssh-keys:remove check_boot".split(" "))
        element = tester.find_element(By.ID, "ssh-key")
        cmd = "echo " + element.text + " | sudo dokku ssh-keys:add check_boot"
        print(cmd)
        ret = os.system(cmd)
        assert ret == 0
        tester.get(sys.argv[1])
    elif id == "list_apps":
        pass
    else:
        raise Exception(id)
    app_name = uuid.uuid4().hex
    tester.log("Making new app %s" % app_name)
    tester.send_keys(By.ID, "id_name", app_name)
    tester.click(By.ID, "create_app")
    tester.wait_for_list([(By.ID, "app_page")])
    assert tester.page_source().find(app_name) != -1

    tester.get(sys.argv[1])
    tester.click(By.XPATH, '//a[text()="wharf"]')
    tester.wait_for_list([(By.ID, "app_page")])
    assert tester.page_source().find("Wharf: wharf") != -1
finally:
    tester.driver.quit()