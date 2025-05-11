from pathlib import Path
import subprocess
from typing import Callable, Literal
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.remote.webdriver import WebDriver
import sys
import os
from subprocess import check_call, check_output
import uuid
import time

class Tester:
    def __init__(self):
        os.environ["MOZ_REMOTE_SETTINGS_DEVTOOLS"] = "1"
        firefox_options = webdriver.FirefoxOptions()
        firefox_options.add_argument("-headless")
        firefox_options.accept_insecure_certs = True
        geckodriver_path = Path("/snap/bin/geckodriver")
        assert geckodriver_path.exists(), geckodriver_path
        self.driver = webdriver.Firefox(options=firefox_options, service=Service(executable_path=geckodriver_path.as_posix(), log_output=subprocess.STDOUT))
        self.driver.implicitly_wait(0)
        self.start = time.time()

    def log(self, message):
        print("%f: %s" % (time.time()-self.start, message))

    def find_one(self, elements: list[WebElement]):
        if len(elements) == 1:
            return elements[0]
        elif len(elements) == 0:
            return None
        else:
            raise Exception(elements)

    def find_element(self, strat: str, id: str | None, allow_none: bool =False):
        self.log("Looking for %s: '%s'" % (strat, id))
        ret = self.find_one(self.driver.find_elements(strat, id))
        if ret is None and not allow_none:
            self.failure()
            raise Exception("No such element with %s and %s" % (strat, id))
        return ret

    def wait_for_one(self, locators):
        for locator in locators:
            element = self.find_element(*locator, allow_none=True)
            if element is not None:
                return element
        return False
    
    def url(self) -> str:
        return self.driver.current_url

    def failure(self):
        self.driver.get_screenshot_as_file("screenshot.png")
        print(self.url())
        print(self.page_source())
        os.system("sudo docker logs wharf.web.1")
        os.system("sudo docker logs wharf.celery.1")
        os.system("dokku nginx:show-config wharf")

    def get(self, url):
        self.log("Went to %s" % url)
        return self.driver.get(url)

    def send_keys(self, strat, id, text):
        self.log("Send keys '%s' to %s: '%s'" % (text, strat, id))
        return self.find_element(strat, id).send_keys(text)
    
    def click(self, strat, id):
        self.log("Click on %s: '%s'" %(strat, id))
        return self.find_element(strat, id).click()
    
    def wait_for_lambda(self, func: Callable[[WebDriver], Literal[False] | WebElement], timeout: int = 10) -> WebElement:
        try:
            return WebDriverWait(self.driver, timeout).until(
                func
            )
        except TimeoutException:
            self.failure()
            raise

    def wait_for_list(self, items, timeout: int=10):
        return self.wait_for_lambda(
                lambda driver: self.wait_for_one(items), timeout
            )

    def get_main_id(self):
        res = self.wait_for_list([(By.ID, "initial-setup-header"), (By.ID, "list_apps")])
        return res.get_attribute("id")
    
    def page_source(self):
        return self.driver.page_source

tester = Tester()
try:
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
        assert element is not None
        cmd = "echo " + element.text + " | sudo dokku ssh-keys:add check_boot"
        tester.log(cmd)
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
    tester.click(By.XPATH, f'//a[text()="{app_name}"]')
    tester.wait_for_list([(By.ID, "app_page")])
    assert tester.page_source().find(f"Wharf: {app_name}") != -1

    github_text = "Can't deploy due to missing GITHUB_URL"
    if tester.page_source().find(github_text) != -1:
        tester.send_keys(By.ID, "id_key", "GITHUB_URL")
        tester.send_keys(By.ID, "id_value", "https://github.com/palfrey/python-getting-started.git")
        tester.click(By.ID, "config_add")

        def wait_for_no_github_text(driver: WebDriver) -> WebElement | Literal[False]:
            if tester.page_source().find(github_text) != -1:
                return False
            else:
                return tester.wait_for_list([(By.ID, "app_page")], timeout=900)

        tester.wait_for_lambda(wait_for_no_github_text, timeout=900)
        if tester.page_source().find("github_text") != -1:
            tester.failure()
            raise Exception
        
    tester.click(By.ID, "deploy_app")
    for x in range(30):
        try:
            tester.log("Attempt %d" % x)
            if tester.url().startswith("https:"):
                tester.log("going to http page")
                tester.get(tester.url().replace("https", "http"))
            tester.wait_for_list([(By.ID, "app_page")], timeout=30)
            break
        except TimeoutException:
            continue
    if tester.page_source().find(f"Wharf: {app_name}") == -1:
        tester.failure()
        raise Exception

finally:
    tester.driver.quit()