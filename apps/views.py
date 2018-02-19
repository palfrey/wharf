from django.shortcuts import render, redirect, reverse
from django.conf import settings
from django.contrib import messages
import wharf.tasks as tasks
from celery.result import AsyncResult
from celery.states import state, PENDING, SUCCESS, FAILURE, STARTED
from django.core.cache import cache

import requests
import time
from . import forms

from redis import StrictRedis

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)

def run_cmd(cmd):
    res = tasks.run_ssh_command.delay(cmd)
    return res.get().strip()

def cmd_key(cmd):
    return "cmd:%s" % cmd

def run_cmd_with_cache(cmd):
    key = cmd_key(cmd)
    existing = cache.get(key)
    if existing:
        return existing
    res = run_cmd(cmd)
    cache.set(key, res, 300)
    return res

def clear_cache(cmd):
    key = cmd_key(cmd)
    cache.delete(key)

def run_cmd_with_log(app, cmd, after):
    if app == None: # global
        app = '_'
    res = tasks.run_ssh_command.delay(cmd)
    return redirect(reverse('wait_for_command', kwargs={'app_name': app, 'task_id': res.id, 'after': after}))

def get_log(res):
    key = tasks.task_key(res.id)
    if res.state > state(PENDING):
        raw = redis.get(key)
        if raw == None:
            return ""
        return raw.decode('utf-8')
    else:
        return ""

def wait_for_command(request, app_name, task_id, after):
    res = AsyncResult(task_id)
    if res.state == state(SUCCESS):
        if app_name == '_': # global
            return redirect(reverse(after, kwargs={'task_id': task_id}))
        else:
            return redirect(reverse(after, kwargs={'app_name': app_name, 'task_id': task_id}))
    log = get_log(res)
    if res.state == state(FAILURE):
        log += str(res.traceback)
    return render(request, 'command_wait.html', {'app': app_name, 'task_id': task_id, 'log': log, 'state': res.state, 'running': res.state in [state(PENDING), state(STARTED)]})

def app_list():
    data = run_cmd_with_cache("apps:list")
    lines = data.split("\n")
    if lines[0] != "=====> My Apps":
        raise Exception(data)
    return lines[1:]

def index(request):
    apps = app_list()
    if request.method == 'POST':
        app_form = forms.CreateAppForm(request.POST)
        if app_form.is_valid():
            return create_app(app_form.cleaned_data['name'])
    else:
        app_form = forms.CreateAppForm()
    config_form = forms.ConfigForm()
    config = global_config()
    return render(request, 'list_apps.html', {'apps': apps, 'app_form': app_form, 'config_form': config_form, 'config': sorted(config.items())})

def generic_config(app, data):
    lines = data.split("\n")
    if lines[0] != "=====> %s env vars" % app:
        raise Exception(data)
    config = {}
    for line in lines[1:]:
        (name, value) = line.split(":", 1)
        config[name] = value.lstrip()
    return config

def app_config(app):
    data = run_cmd_with_cache("config %s" % app)
    return generic_config(app, data)

def global_config():
    data = run_cmd_with_cache("config --global")
    return generic_config("global", data)

def app_config_set(app, key, value):
    return run_cmd_with_log(app, "config:set %s %s=%s" % (app, key, value), "check_app_config_set")

def check_config_set(request, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    lines = data.split("\n")
    if lines[0] != '-----> Setting config vars':
        raise Exception(data)
    messages.success(request, 'Config updated')

def check_app_config_set(request, app_name, task_id):
    check_config_set(request, task_id)
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))

def global_config_set(request):
    form = forms.ConfigForm(request.POST)
    if form.is_valid():
        return run_cmd_with_log(None, "config:set --global %s=%s" % (form.cleaned_data['key'], form.cleaned_data['value']), "check_global_config_set")
    else:
        raise Exception

def check_global_config_set(request, task_id):
    check_config_set(request, task_id)
    clear_cache("config --global")
    return redirect(reverse('index'))

def generic_list(app_name, data, name_field, fields):
    lines = data.split("\n")
    if lines[0].find("is not a dokku command") != -1:
        raise Exception("Need plugin!")
    if lines[0].find("There are no") != -1:
        return None
    fields = dict([[x,{}] for x in fields])
    last_field = None
    for f in fields.keys():
        index = lines[0].find(f)
        if index == -1:
            raise Exception("Can't find '%s' in '%s'" % (f, lines[0].strip()))
        if f == name_field:
            index = 0
        fields[f]["start"] = index
        if last_field != None:
            fields[last_field]["end"] = index
        last_field = f
    fields[last_field]["end"] = None
    results = []
    for line in lines[1:]:
        info = {}
        for f in fields.keys():
            if fields[f]["end"] == None:
                info[f] = line[fields[f]["start"]:].strip()
            else:
                info[f] = line[fields[f]["start"]:fields[f]["end"]].strip()
        results.append(info)
    results = dict([[x[name_field], x] for x in results])
    if app_name in results:
        return results[app_name]
    else:
        return None

def db_list(app_name, data):
    return generic_list(app_name, data, "NAME", ["NAME", "VERSION", "STATUS", "EXPOSED PORTS", "LINKS"])

def postgres_list(app_name):
    data = run_cmd_with_cache("postgres:list")
    try:
        return db_list(app_name, data)
    except:
        clear_cache("postgres:list")
        raise

def redis_list(app_name):
    data = run_cmd_with_cache("redis:list")
    try:
        return db_list(app_name, data)
    except:
        clear_cache("redis:list")
        raise

def letsencrypt(app_name):
    data = run_cmd_with_cache("letsencrypt:ls")
    return generic_list(app_name, data, "App name", ["App name", "Certificate Expiry", "Time before expiry", "Time before renewal"])

def app_info(request, app_name):
    config = app_config(app_name)
    if request.method == 'POST':
        form = forms.ConfigForm(request.POST)
        if form.is_valid():
            return app_config_set(app_name, form.cleaned_data['key'], form.cleaned_data['value'])
    else:
        form = forms.ConfigForm()
    return render(request, 'app_info.html', {
        'postgres': postgres_list(app_name),
        'redis': redis_list(app_name),
        'letsencrypt': letsencrypt(app_name),
        'form': form,
        'app': app_name,
        'git_url': config.get('GITHUB_URL', None),
        'config': sorted(config.items())
    })

def deploy(request, app_name):
    res = tasks.deploy.delay(app_name, request.POST['url'])
    clear_cache("config %s" % app_name)
    return redirect(reverse('wait_for_command', kwargs={'app_name': app_name, 'task_id': res.id, 'after': "check_deploy"}))

def create_postgres(request, app_name):
    return run_cmd_with_log(app_name, ["postgres:create %s" % app_name, "postgres:link %s %s" % (app_name, app_name)], "check_postgres")

def create_redis(request, app_name):
    return run_cmd_with_log(app_name, ["redis:create %s" % app_name, "redis:link %s %s" % (app_name, app_name)], "check_redis")

def check_deploy(request, app_name, task_id):
    clear_cache("config %s" % app_name)
    messages.success(request, "%s redeployed" % app_name)
    return redirect(reverse('app_info', args=[app_name]))

def check_postgres(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Postgres container created") == -1:
        raise Exception(data)
    messages.success(request, "Postgres added to %s" % app_name)
    clear_cache("postgres:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))

def check_redis(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Redis container created") == -1:
        raise Exception(data)
    messages.success(request, "Redis added to %s" % app_name)
    clear_cache("redis:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))

def create_app(app_name):
    return run_cmd_with_log(app_name, "apps:create %s" % app_name, "check_app")

def check_app(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Creating %s... done" % app_name) == -1:
        raise Exception(data)
    messages.success(request, "Created %s" % app_name)
    clear_cache("apps:list")
    return redirect(reverse('app_info', args=[app_name]))

def setup_letsencrypt(request, app_name):
    return run_cmd_with_log(app_name, "letsencrypt %s" % app_name, "check_letsencrypt")

def check_letsencrypt(request, app_name, task_id):
    res = AsyncResult(task_id)
    log = get_log(res)
    if log.find("Certificate retrieved successfully") !=-1:
        clear_cache("letsencrypt:ls")
        return redirect(reverse('app_info', args=[app_name]))
    else:
        return render(request, 'command_wait.html', {'app': app_name, 'task_id': task_id, 'log': log, 'state': res.state, 'running': res.state in [state(PENDING), state(STARTED)]})