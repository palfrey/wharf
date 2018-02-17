from django.shortcuts import render, redirect, reverse
from django.conf import settings
from django.contrib import messages
import wharf.tasks as tasks
from celery.result import AsyncResult
from celery.states import state, PENDING, SUCCESS

import requests
import time
from . import forms

from redis import StrictRedis

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)

def run_cmd(cmd):
    res = tasks.run_command.delay(cmd)
    return res.get().strip()

def run_cmd_with_log(app, cmd, after):
    res = tasks.run_command.delay(cmd)
    return redirect(reverse('wait_for_command', kwargs={'app_name': app, 'task_id': res.id, 'after': after}))

def get_log(res):
    key = tasks.task_key(res.id)
    if res.state > state(PENDING):
        raw = redis.get(key)
        if raw == None:
            return None
        return raw.decode('utf-8')
    else:
        return ""

def wait_for_command(request, app_name, task_id, after):
    res = AsyncResult(task_id)
    if res.state == state(SUCCESS):
        return redirect(reverse(after, kwargs={'app_name': app_name, 'task_id': task_id}))
    log = get_log(res)
    return render(request, 'command_wait.html', {'app': app_name, 'task_id': task_id, 'log': log, 'state': res.state})

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
    return run_cmd_with_log(app, "config:set %s %s=%s" % (app, key, value), "check_app_config_set")

def check_app_config_set(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    lines = data.split("\n")
    if lines[0] != '-----> Setting config vars':
        raise Exception(data)
    messages.success(request, 'Config updated')
    return redirect(reverse('app_info', args=[app_name]))

def app_info(request, app_name):
    config = app_config(app_name)
    if request.method == 'POST':
        form = forms.ConfigForm(request.POST)
        if form.is_valid():
            return app_config_set(app_name, form.cleaned_data['key'], form.cleaned_data['value'])
    else:
        form = forms.ConfigForm()
    return render(request, 'app_info.html', {'form': form, 'app': app_name, 'config': sorted(config.items())})
