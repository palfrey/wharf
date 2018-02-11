from django.shortcuts import render, redirect, reverse
from django.conf import settings
import wharf.tasks as tasks

import requests
import time
from . import forms

def run_cmd(cmd):
    res = tasks.run_command.delay(cmd)
    return res.get().strip()

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

def app_config_set(app, key, value):
    data = run_cmd("config:set %s %s=%s" % (app, key, value))
    lines = data.split("\n")
    if lines[0] != '-----> Setting config vars':
        raise Exception(data)

def app_info(request, app_name):
    config = app_config(app_name)
    if request.method == 'POST':
        form = forms.ConfigForm(request.POST)
        if form.is_valid():
            app_config_set(app_name, form.cleaned_data['key'], form.cleaned_data['value'])
            return redirect(reverse('app_info', args=[app_name]))
    else:
        form = forms.ConfigForm()
    return render(request, 'app_info.html', {'form': form, 'app': app_name, 'config': sorted(config.items())})
