from flask import Flask, render_template
import requests
import time

app = Flask(__name__)

DOKKU_API = "http://127.0.0.1:34720"
API_KEY = "dffbadf9726c5d57a5257b89c0f885ec"
API_SECRET = "3ba0f24046cb61754ab0b30a41398c4a"
headers = {"Api-Key": API_KEY, "Api-Secret": API_SECRET}

def run_cmd(cmd):
    req = requests.post("%s/commands" % DOKKU_API, headers=headers, data="cmd=%s" % cmd)
    req.raise_for_status()
    token = req.json()['token']
    while True:
        req = requests.get("%s/commands/%s" % (DOKKU_API, token), headers=headers)
        req.raise_for_status()
        if req.json()['ran_at'] != None:
            break
        time.sleep(0.1)
    if not req.json()['result_data']['ok']:
        raise Exception(req.json())
    return req.json()['result_data']['output']

def app_list():
    data = run_cmd("apps:list")
    lines = data.split("\n")
    if lines[0] != "=====> My Apps":
        raise Exception(data)
    return lines[1:]

@app.route("/")
def index():
    apps = app_list()
    return render_template('list_apps.html', apps=apps)

def app_config(app):
    data = run_cmd("config %s" % app)
    lines = data.split("\n")
    if lines[0] != "=====> %s env vars" % app:
        raise Exception(data)
    config = {}
    for line in lines[1:]:
        (name, value) = line.split(":", 1)
        config[name] = value.lstrip()
    return config

@app.route("/apps/<app_name>")
def app_info(app_name):
    config = app_config(app_name)
    return render_template('app_info.html', app=app_name, config=sorted(config.items()))