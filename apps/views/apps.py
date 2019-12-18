from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, reverse
from django.contrib import messages
from celery.states import state, FAILURE
from django.http import HttpResponseBadRequest, HttpResponse, HttpResponseServerError
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from ..models import App, TaskLog
from ..forms import ConfigFormBulk, CreateDomainForm, CreateAppForm, ConfigForm
from . import config as configuration, commands, buildpacks, postgres, mariadb, redis, letsencrypt, domains, utils, cache

import wharf.tasks as tasks
import re
import json
import hmac
import hashlib
import timeout_decorator

ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')


@login_required(login_url='/accounts/login/')
def app_info(request, app_name):
    app, _ = App.objects.get_or_create(name=app_name)
    config = configuration.app_config(app_name)

    if "GITHUB_URL" in config:
        app.github_url = config["GITHUB_URL"]
        app.save()
    if request.method == 'POST':

        form = ConfigFormBulk(request.POST)

        if form.is_valid():
            cmd_string = config.format_config_string(form.cleaned_data['userInput'])

            if not cmd_string:
                raise Exception("The input is invalid")

            return commands.run_cmd_with_log(
                app_name,
                "Setting app configuration",
                "config:set %s %s" % (app_name, cmd_string),
                "check_app_config_set"
            )
    else:
        form = ConfigFormBulk()

    original_buildpack_items = buildpacks.buildpack_list(app_name)
    original_postgres_items = postgres.postgres_list(app_name)
    original_mariadb_items = mariadb.mariadb_list(app_name)

    list_postgres = []
    list_mariadb = []

    if type(original_postgres_items) is dict:
        list_postgres.append(postgres.postgres_list(app_name))
    else:
        list_postgres = original_postgres_items

    if type(original_mariadb_items) is dict:
        list_mariadb.append(mariadb.mariadb_list(app_name))
    else:
        list_mariadb = original_mariadb_items

    return render(
        request,
        'app_info.html', {
            'postgres': list_postgres,
            'redis': redis.redis_list(app_name),
            'mariadb': list_mariadb,
            'letsencrypt': letsencrypt.letsencrypt(app_name),
            'buildpacks': original_buildpack_items,
            # 'process': process_info(app_name),
            # 'logs': ansi_escape.sub("", run_cmd("logs %s --num 100" % app_name)),
            'domains': domains.domains_list(app_name),
            'domain_form': CreateDomainForm(),
            'config_bulk_form': form,
            'app': app_name,
            'git_url': config.get('GITHUB_URL', None),
            'config': sorted(config.items()),
            'task_logs': TaskLog.objects.filter(app=app).order_by('-when').all(),
        }
    )


def create_app(app_name):
    App(name=app_name).save()
    return commands.run_cmd_with_log(
        app_name,
        "Add app %s" % app_name,
        "apps:create %s" % app_name,
        "check_app"
    )


def check_app(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("Creating %s... done" % app_name) == -1:
        raise Exception(data)
    messages.success(request, "Created %s" % app_name)
    cache.clear_cache("apps:list")
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )


def app_list():
    data = commands.run_cmd_with_cache("apps:list")
    lines = data.split("\n")
    if lines[0] != "=====> My Apps":
        raise Exception(data)
    return lines[1:]


@login_required(login_url='/accounts/login/')
def index(request):
    try:
        apps = app_list()
    except Exception as e:
        if e.__class__.__name__ in ["AuthenticationException"]:  # Can't use class directly as Celery mangles things
            return render(request, 'setup_key.html', {'key': tasks.get_public_key.delay().get()})
        else:
            raise
    if request.method == 'POST':
        app_form = CreateAppForm(request.POST)
        if app_form.is_valid():
            return create_app(app_form.cleaned_data['name'])
    else:
        app_form = CreateAppForm()
    config_form = ConfigForm()
    config_bulk_form = ConfigFormBulk()
    config = configuration.global_config()
    return render(
        request,
        'list_apps.html',
        {
            'apps': apps,
            'app_form': app_form,
            'config_form': config_form,
            'config_bulk_form': config_bulk_form,
            'config': sorted(config.items())
        }
    )


@login_required(login_url='/accounts/login/')
def show_log(request, task_id):
    res = AsyncResult(task_id)
    task = TaskLog.objects.get(task_id=task_id)
    log = ansi_escape.sub("", utils.get_log(res))
    if res.state == state(FAILURE):
        log += str(res.traceback)
    return render(
        request,
        'command_wait.html', {
            'app': task.app.name,
            'task_id': task_id,
            'log': log,
            'state': res.state,
            'running': False,
            'description': task.description
        }
    )


def process_info(app_name):
    data = commands.run_cmd_with_cache("ps:report %s" % app_name)
    lines = data.split("\n")
    if lines[0].find("%s process information" % app_name) == -1 and lines[0].find(
            "%s ps information" % app_name) == -1:  # Different versions
        raise Exception(data)
    results = {}
    processes = {}
    process_re = re.compile("Status\s+([^\.]+\.\d+):?\s+(\S+)")
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


@login_required(login_url='/accounts/login/')
def deploy(request, app_name):
    if request.POST['action'] == "deploy":
        res = tasks.deploy.delay(app_name, request.POST['url'])
        cache.clear_cache("config %s" % app_name)
        cache.clear_cache("domains:report %s" % app_name)
        cache.clear_cache("ps:report %s" % app_name)
        return redirect(
            reverse('wait_for_command', kwargs={'app_name': app_name, 'task_id': res.id, 'after': "check_deploy"}))
    elif request.POST['action'] == "rebuild":
        return commands.run_cmd_with_log(app_name, "Rebuilding", "ps:rebuild %s" % app_name, "check_rebuild")
    else:
        raise Exception(request.POST['action'])


def check_deploy(request, app_name, task_id):
    cache.clear_cache("config %s" % app_name)
    messages.success(request, "%s redeployed" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_rebuild(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("Application deployed:") == -1:
        raise Exception(data)
    messages.success(request, "%s rebuilt" % app_name)
    cache.clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


@csrf_exempt
def github_webhook(request):
    secret = settings.GITHUB_SECRET.encode('utf-8')
    hash = "sha1=%s" % hmac.new(secret, request.body, hashlib.sha1).hexdigest()
    if "HTTP_X_HUB_SIGNATURE" not in request.META:
        return HttpResponseBadRequest("No X-Hub-Signature header")
    header = request.META["HTTP_X_HUB_SIGNATURE"]
    if header != hash:
        return HttpResponseBadRequest("%s doesn't equal %s" % (hash, header))
    data = json.loads(request.read())
    if "hook_id" in data:  # assume Ping
        if "push" not in data["hook"]["events"]:
            return HttpResponseBadRequest("No Push event set!")
        return HttpResponse("All good")
    default_ref = "refs/heads/%s" % data["repository"]["default_branch"]
    if data["ref"] != default_ref:
        return HttpResponse("Push to non-default branch (saw %s, expected %s)" % (data["ref"], default_ref))
    clone_url = data["repository"]["clone_url"]
    apps = App.objects.filter(github_url=clone_url)
    if not apps.exists():
        return HttpResponseBadRequest("Can't find an entry for clone URL %s" % clone_url)
    app = apps.first()
    res = tasks.deploy.delay(app.name, clone_url)
    cache.clear_cache("config %s" % app.name)
    return HttpResponse(
        "Running deploy. Deploy log is at %s" % request.build_absolute_uri(
            reverse(
                'show_log',
                kwargs={
                    'task_id': res.id
                }
            )
        )
    )