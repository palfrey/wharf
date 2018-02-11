from django.shortcuts import render
from django.conf import settings

import requests
import time

def run_cmd(cmd):
    req = requests.post("%s/commands" % settings.DOKKU_API, headers=settings.DOKKU_HEADERS, data="cmd=%s" % cmd)
    req.raise_for_status()
    token = req.json()['token']
    while True:
        req = requests.get("%s/commands/%s" % (settings.DOKKU_API, token), headers=settings.DOKKU_HEADERS)
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

def index(request):
    apps = app_list()
    return render(request, 'list_apps.html', {'apps': apps})

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

def app_info(request, app_name):
    config = app_config(app_name)
    return render(request, 'app_info.html', { 'app': app_name, 'config': sorted(config.items())})
