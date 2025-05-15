from typing import Any, Sequence, cast
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
import wharf.tasks as tasks
from celery.result import AsyncResult
from celery.states import state, PENDING, SUCCESS, FAILURE, STARTED
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest, HttpResponseBadRequest, HttpResponse, HttpResponseServerError

from . import forms
from . import models
import re
from datetime import datetime
import json
import hmac
import hashlib
import timeout_decorator
from packaging.version import Version

from redis import StrictRedis

from logging import getLogger

logger = getLogger(__name__)

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)
ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

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
    cache.set(key, res, None)
    return res

def clear_cache(cmd):
    key = cmd_key(cmd)
    cache.delete(key)

def plugin_versions() -> dict[str, Version]:
    plugin_raw_list = run_cmd_with_cache("plugin:list")
    plugin_pattern = re.compile(r"([a-z\-_0-9]+?)\s+([\d\.]+)")
    plugin_groups = plugin_pattern.findall(plugin_raw_list)
    return dict([(k, Version(v)) for (k,v) in plugin_groups])

def redirect_reverse(view_name: str, kwargs: dict[str, Any] | None = None, args: Sequence[Any] | None = None):
    new_url = reverse(view_name, kwargs=kwargs, args=args)
    logger.warning(f"New url is {new_url}")
    return redirect(new_url)

def run_cmd_with_log(app_name, description, cmd, after):
    res = tasks.run_ssh_command.delay(cmd)
    if app_name == None: # global
        app_name = '_'
    else:
        models.TaskLog(
            task_id=res.id,
            when=datetime.now(),
            app=models.App.objects.get(name=app_name),
            description=description
        ).save()
    return redirect_reverse('wait_for_command', kwargs={'app_name': app_name, 'task_id': res.id, 'after': after})

def get_log(res: AsyncResult):
    if res.state > state(PENDING):
        key = tasks.task_key(res.id)
        raw = cast(bytes | None, redis.get(key))
        if raw is None:
            return ""
        return raw.decode('utf-8')
    else:
        return ""

def wait_for_command(request: HttpRequest, app_name, task_id, after):
    res = AsyncResult(task_id)
    if app_name != '_':
        app = models.App.objects.get(name=app_name)
        task, created = models.TaskLog.objects.get_or_create(task_id=task_id, defaults={'app': app, 'when': datetime.now()})
        description = task.description
    else:
        description = ""
    if res.state == state(SUCCESS):
        return redirect_reverse(after, kwargs={'app_name': app_name, 'task_id': task_id})
    log = ansi_escape.sub("", get_log(res))
    if res.state == state(FAILURE):
        log += str(res.traceback)
    return render(request, 'command_wait.html', {
        'app': app_name,
        'task_id': task_id,
        'log': log,
        'state': res.state,
        'running': res.state in [state(PENDING), state(STARTED)],
        'description': description
        })

def show_log(request: HttpRequest, task_id: str):
    res = AsyncResult(task_id)
    task = models.TaskLog.objects.get(task_id=task_id)
    log = ansi_escape.sub("", get_log(res))
    if res.state == state(FAILURE):
        log += str(res.traceback)
    return render(request, 'command_wait.html', {
        'app': task.app.name,
        'task_id': task_id,
        'log': log,
        'state': res.state,
        'running': False,
        'description': task.description})

def app_list():
    data = run_cmd_with_cache("apps:list")
    lines = data.split("\n")
    if lines[0] != "=====> My Apps":
        raise Exception(data)
    return lines[1:]

def index(request: HttpRequest):
    try:
        apps = app_list()
    except Exception as e:
        if e.__class__.__name__ in ["AuthenticationException"]: # Can't use class directly as Celery mangles things
            return render(request, 'setup_key.html', {'key': tasks.get_public_key.delay().get()})
        else:
            raise
    if request.method == 'POST':
        app_form = forms.CreateAppForm(request.POST)
        if app_form.is_valid():
            return create_app(app_form.cleaned_data['name'])
    else:
        app_form = forms.CreateAppForm()
    config_form = forms.ConfigForm()
    config = global_config()
    return render(request, 'list_apps.html', {'apps': apps, 'app_form': app_form, 'config_form': config_form, 'config': sorted(config.items())})

def refresh_all(request: HttpRequest):
    cache.clear()
    return redirect_reverse('index')

def generic_config(app_name: str, data: str) -> dict[str, Any]:
    if "does not exist" in data:
        return {}
    lines = data.split("\n")
    if lines[0] != "=====> %s env vars" % app_name:
        raise Exception(data)
    config = {}
    for line in lines[1:]:
        (name, value) = line.split(":", 1)
        config[name] = value.lstrip()
    return config

def app_config(app_name):
    data = run_cmd_with_cache("config %s" % app_name)
    return generic_config(app_name, data)

def global_config():
    data = run_cmd_with_cache("config --global")
    return generic_config("global", data)

def app_config_set(app, key, value):
    return run_cmd_with_log(app, "Setting %s" % key, "config:set %s %s=%s" % (app, key, value), "check_app_config_set")

def check_config_set(request: HttpRequest, task_id: str):
    res = AsyncResult(task_id)
    data = get_log(res)
    lines = data.split("\n")
    if lines[0] != '-----> Setting config vars':
        raise Exception(data)
    messages.success(request, 'Config updated')

def check_app_config_set(request: HttpRequest, app_name, task_id: str):
    check_config_set(request, task_id)
    clear_cache("config %s" % app_name)
    return redirect_reverse('app_info', args=[app_name])

def global_config_set(request):
    form = forms.ConfigForm(request.POST)
    if form.is_valid():
        return run_cmd_with_log(None, "Setting %s" % form.cleaned_data['key'], "config:set --global %s=%s" % (form.cleaned_data['key'], form.cleaned_data['value']), "check_global_config_set")
    else:
        raise Exception

def check_global_config_set(request: HttpRequest, task_id: str):
    check_config_set(request, task_id)
    clear_cache("config --global")
    return redirect_reverse('index')

def generic_list(app_name, data, name_field: str, field_names: list[str]):
    lines = data.split("\n")
    if lines[0].find("is not a dokku command") != -1:
        raise Exception("Neeed plugin!")
    if lines[0].find("does") != -1:
        return None
    fields = dict([(x,{}) for x in field_names])
    last_field: str | None = None
    for f in fields.keys():
        index = lines[0].find(f)
        if index == -1:
            raise Exception("Can't find '%s' in '%s'" % (f, lines[0].strip()))
        if f == name_field:
            index = 0
        fields[f]["start"] = index
        if last_field is not None:
            fields[last_field]["end"] = index
        last_field = f
    assert last_field is not None
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
    
def generic_info(data: str):
    lines = data.split("\n")
    if lines[0].find("is not a dokku command") != -1:
        raise Exception("Neeed plugin!")
    if lines[0].find("does not exist") != -1:
        return None
    results = {}
    for line in lines[1:]:
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        results[key] = value
    return results

def db_info(cache_key: str):
    data = run_cmd_with_cache(cache_key)
    try:
        return generic_info(data)
    except:
        clear_cache(cache_key)
        raise

def postgres_info(app_name: str):
    cache_key = "postgres:info %s" % app_name
    return db_info(cache_key)

def redis_info(app_name: str):
    cache_key = "redis:info %s" % app_name
    return db_info(cache_key)

def letsencrypt_command():
    version = plugin_versions().get("letsencrypt")
    if version is None:
        return None
    if version <= Version("0.9.4"):
        return "letsencrypt:ls"
    else:
        return "letsencrypt:list"

def letsencrypt(app_name: str):
    data = run_cmd_with_cache(letsencrypt_command())
    return generic_list(app_name, data, "App name", ["App name", "Certificate Expiry", "Time before expiry", "Time before renewal"])

def process_info(app_name):
    data = run_cmd_with_cache("ps:report %s" % app_name)
    if "does not exist" in data:
        return {}    
    lines = data.split("\n")
    if lines[0].find("exit status") != -1:
        lines = lines[1:]
    if lines[0].find("%s process information" % app_name) == -1 and lines[0].find("%s ps information" % app_name) == -1: # Different versions
        raise Exception(data)
    results = {}
    processes = {}
    process_re = re.compile(r"Status\s+(\S+ \d+):\s+(\S+) \(CID: [a-z0-9]+\)")
    for line in lines[1:]:
        if line.strip().startswith("Status "):
            matches = process_re.search(line)
            if matches == None:
                raise Exception(line)
            matches = matches.groups()
            processes[matches[0]] = matches[1]
        else:
            (name, rest) = line.split(":", 1)
            results[name.strip()] = rest.strip()
    results["processes"] = processes
    return results

def domains_list(app_name: str) -> list[str]:
    data = run_cmd_with_cache("domains:report %s" % app_name)
    if "does not exist" in data:
        return []    
    vhosts = re.search("Domains app vhosts: (.*)", data)
    assert vhosts is not None
    return [x.strip() for x in vhosts.groups()[0].split(" ") if x != ""]

def add_domain(request: HttpRequest, app_name: str):
    form = forms.CreateDomainForm(request.POST)
    if form.is_valid():
        commands = ["domains:add %s %s" % (app_name, form.cleaned_data['name'])]
        if letsencrypt(app_name) != None:
            commands.append("letsencrypt %s" % app_name)
        return run_cmd_with_log(app_name, "Add domain %s" % form.cleaned_data['name'], commands, "check_domain")
    else:
        raise Exception

def check_domain(request: HttpRequest, app_name, task_id: str):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Reloading nginx") != -1:
        clear_cache("domains:report %s" % app_name)
        messages.success(request, "Added domain name to %s" % app_name)
        return redirect_reverse('app_info', args=[app_name])
    else:
        raise Exception(data)

def remove_domain(request: HttpRequest, app_name):
    name = request.POST['name']
    commands = ["domains:remove %s %s" % (app_name, name)]
    if letsencrypt(app_name) != None:
        commands.append("letsencrypt %s" % app_name)
    return run_cmd_with_log(app_name, "Remove domain %s" % name, commands, "check_domain")

def app_info(request: HttpRequest, app_name):
    app, _ = models.App.objects.get_or_create(name=app_name)
    config = app_config(app_name)
    if "GITHUB_URL" in config:
        app.github_url = config["GITHUB_URL"]
        app.save()
    if request.method == 'POST':
        form = forms.ConfigForm(request.POST)
        if form.is_valid():
            return app_config_set(app_name, form.cleaned_data['key'], form.cleaned_data['value'])
    else:
        form = forms.ConfigForm()
    return render(request, 'app_info.html', {
        'postgres': postgres_info(app_name),
        'redis': redis_info(app_name),
        'letsencrypt': letsencrypt(app_name),
        'process': process_info(app_name),
        'logs': ansi_escape.sub("", run_cmd("logs %s --num 100" % app_name)),
        'domains': domains_list(app_name),
        'domain_form': forms.CreateDomainForm(),
        'form': form,
        'app': app_name,
        'git_url': config.get('GITHUB_URL', None),
        'config': sorted(config.items()),
        'task_logs': models.TaskLog.objects.filter(app=app).order_by('-when').all(),
    })

def deploy(request: HttpRequest, app_name):
    if request.POST['action'] == "deploy":
        res = tasks.deploy.delay(app_name, request.POST['url'])
        clear_cache("config %s" % app_name)
        clear_cache("domains:report %s" % app_name)
        clear_cache("ps:report %s" % app_name)
        return redirect_reverse('wait_for_command', kwargs={'app_name': app_name, 'task_id': res.id, 'after': "check_deploy"})
    elif request.POST['action'] == "rebuild":
        return run_cmd_with_log(app_name, "Rebuilding", "ps:rebuild %s" % app_name, "check_rebuild")
    else:
        raise Exception(request.POST['action'])

def create_postgres(request: HttpRequest, app_name):
    return run_cmd_with_log(app_name, "Add Postgres", ["postgres:create %s" % app_name, "postgres:link %s %s" % (app_name, app_name)], "check_postgres")

def create_redis(request: HttpRequest, app_name):
    return run_cmd_with_log(app_name, "Add Redis", ["redis:create %s" % app_name, "redis:link %s %s" % (app_name, app_name)], "check_redis")

def check_deploy(request: HttpRequest, app_name, task_id: str):
    clear_cache("config %s" % app_name)
    messages.success(request, "%s redeployed" % app_name)
    return redirect_reverse('app_info', args=[app_name])

def check_rebuild(request: HttpRequest, app_name, task_id: str):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Application deployed:") == -1:
        raise Exception(data)
    messages.success(request, "%s rebuilt" % app_name)
    clear_cache("config %s" % app_name)
    return redirect_reverse('app_info', args=[app_name])

def check_postgres(request: HttpRequest, app_name, task_id: str):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Postgres container created") == -1:
        raise Exception(data)
    messages.success(request, "Postgres added to %s" % app_name)
    clear_cache("postgres:list")
    clear_cache("config %s" % app_name)
    return redirect_reverse('app_info', args=[app_name])

def check_redis(request: HttpRequest, app_name, task_id: str):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Redis container created") == -1:
        raise Exception(data)
    messages.success(request, "Redis added to %s" % app_name)
    clear_cache("redis:list")
    clear_cache("config %s" % app_name)
    return redirect_reverse('app_info', args=[app_name])

def create_app(app_name: str):
    if models.App.objects.filter(name=app_name).exists():
        return HttpResponseBadRequest(f"You already have an app called '{app_name}'")
    models.App(name=app_name).save()
    return run_cmd_with_log(app_name, "Add app %s" % app_name, "apps:create %s" % app_name, "check_app")

def check_app(request: HttpRequest, app_name: str, task_id: str):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Creating %s..." % app_name) == -1:
        raise Exception(data)
    messages.success(request, "Created %s" % app_name)
    clear_cache("apps:list")
    return redirect_reverse('app_info', args=[app_name])

def setup_letsencrypt(request: HttpRequest, app_name: str):
    return run_cmd_with_log(app_name, "Enable Let's Encrypt", "letsencrypt %s" % app_name, "check_letsencrypt")

def check_letsencrypt(request: HttpRequest, app_name: str, task_id: str):
    res = AsyncResult(task_id)
    log = get_log(res)
    if log.find("Certificate retrieved successfully") !=-1:
        clear_cache(letsencrypt_command())
        return redirect_reverse('app_info', args=[app_name])
    else:
        return render(request, 'command_wait.html', {'app': app_name, 'task_id': task_id, 'log': log, 'state': res.state, 'running': res.state in [state(PENDING), state(STARTED)]})

@csrf_exempt
def github_webhook(request: HttpRequest):
    secret = settings.GITHUB_SECRET.encode('utf-8')
    hash = "sha1=%s" % hmac.new(secret, request.body, hashlib.sha1).hexdigest()
    if "HTTP_X_HUB_SIGNATURE" not in request.META:
        return HttpResponseBadRequest("No X-Hub-Signature header")
    header = request.META["HTTP_X_HUB_SIGNATURE"]
    if header != hash:
        return HttpResponseBadRequest("%s doesn't equal %s" % (hash, header))
    data = json.loads(request.read())
    if "hook_id" in data: # assume Ping
        if "push" not in data["hook"]["events"]:
            return HttpResponseBadRequest("No Push event set!")
        return HttpResponse("All good")
    default_ref = "refs/heads/%s" % data["repository"]["default_branch"]
    if data["ref"] != default_ref:
        return HttpResponse("Push to non-default branch (saw %s, expected %s)" % (data["ref"], default_ref))
    clone_url = data["repository"]["clone_url"]
    apps = models.App.objects.filter(github_url=clone_url)
    if not apps.exists():
        return HttpResponseBadRequest("Can't find an entry for clone URL %s" % clone_url)
    app = apps.first()
    assert app is not None
    res = tasks.deploy.delay(app.name, clone_url)
    clear_cache("config %s" % app.name)
    return HttpResponse("Running deploy. Deploy log is at %s" % request.build_absolute_uri(reverse('show_log', kwargs={'task_id': res.id})))

@timeout_decorator.timeout(5, use_signals=False)
def check_status():
    # Clearing the cache and then trying a command makes sure that
    # - The cache is up
    # - Celery is up
    # - We can run dokku commands
    clear_cache("config --global")
    run_cmd_with_cache("config --global")

def status(request: HttpRequest):
    try:
        check_status()
        return HttpResponse("All good")
    except timeout_decorator.TimeoutError:
        return HttpResponseServerError("Timeout trying to get status")