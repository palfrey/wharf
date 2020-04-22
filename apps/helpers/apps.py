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

ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')


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
