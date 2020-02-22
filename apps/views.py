from django.shortcuts import render, redirect, reverse
from django.conf import settings
from django.contrib import messages
import wharf.tasks as tasks
from celery.result import AsyncResult
from celery.states import state, PENDING, SUCCESS, FAILURE, STARTED
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseBadRequest, HttpResponse, HttpResponseServerError
from django.contrib.auth.decorators import login_required
from pprint import pprint

import requests
import time
from . import forms
from . import models
import re
from datetime import datetime
import json
import hmac
import hashlib
import timeout_decorator

from redis import StrictRedis

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


def run_cmd_with_log(app_name, description, cmd, after):
    res = tasks.run_ssh_command.delay(cmd)
    if app_name == None:  # global
        app_name = '_'
    else:
        models.TaskLog(
            task_id=res.id,
            when=datetime.now(),
            app=models.App.objects.get(name=app_name),
            description=description
        ).save()

    return redirect(reverse('wait_for_command', kwargs={'app_name': app_name, 'task_id': res.id, 'after': after}))


def get_log(res):
    key = tasks.task_key(res.id)
    if res.state > state(PENDING):
        raw = redis.get(key)
        if raw == None:
            return ""
        return raw.decode('utf-8')
    else:
        return ""


@login_required(login_url='/accounts/login/')
def wait_for_command(request, app_name, task_id, after):
    res = AsyncResult(task_id)
    if app_name != '_':
        app = models.App.objects.get(name=app_name)
        task, created = models.TaskLog.objects.get_or_create(task_id=task_id,
                                                             defaults={'app': app, 'when': datetime.now()})
        description = task.description
    else:
        description = ""
    if res.state == state(SUCCESS):
        return redirect(reverse(after, kwargs={'app_name': app_name, 'task_id': task_id}))
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


@login_required(login_url='/accounts/login/')
def show_log(request, task_id):
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
        app_form = forms.CreateAppForm(request.POST)
        if app_form.is_valid():
            return create_app(app_form.cleaned_data['name'])
    else:
        app_form = forms.CreateAppForm()

    return render(request, 'dashboard.html', {
        'apps': apps,
        'app_form': app_form,
    })


@login_required(login_url='/accounts/login/')
def apps_list(request):
    """
    Renders the application list
    """
    try:
        apps = app_list()
    except Exception as e:
        if e.__class__.__name__ in ["AuthenticationException"]:  # Can't use class directly as Celery mangles things
            return render(request, 'setup_key.html', {'key': tasks.get_public_key.delay().get()})
        else:
            raise
    return render(request, 'apps_list.html', {
        'apps': apps
    })


@login_required(login_url='/accounts/login')
def global_variables_list(request):
    """
    Renders the global variables list
    """
    try:
        global_env_vars_list = global_config()
    except Exception as e:
        if e.__class__.__name__ in ["AuthenticationException"]:  # Can't use class directly as Celery mangles things
            return render(request, 'setup_key.html', {'key': tasks.get_public_key.delay().get()})
        else:
            raise

    return render(request, 'global_env_vars_list.html', {
        'config': sorted(global_env_vars_list.items())
    })


@login_required(login_url='/accounts/login')
def app_configuration(request, app_name):
    """
    Renders the application links and buildpacks
    """
    original_buildpack_items = buildpack_list(app_name)
    original_postgres_items = postgres_list(app_name)
    original_mariadb_items = mariadb_list(app_name)
    list_postgres = []
    list_mariadb = []

    if type(original_postgres_items) is dict:
        list_postgres.append(postgres_list(app_name))
    else:
        list_postgres = original_postgres_items

    if type(original_mariadb_items) is dict:
        list_mariadb.append(mariadb_list(app_name))
    else:
        list_mariadb = original_mariadb_items

    app_links = {
        'postgres': list_postgres,
        'redis': redis_list(app_name),
        'mariadb': list_mariadb,
        'buildpacks': original_buildpack_items,
    }

    return render(request, 'app_configuration.html', {
        'app_links': app_links,
        'app_name': app_name
    })


@login_required(login_url='/accounts/login/')
def refresh_all(request):
    cache.clear()
    return redirect(reverse('index'))


def generic_config(app, data):
    lines = data.split("\n")
    if lines[0] != "=====> %s env vars" % app:
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


def check_config_set(request, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    lines = data.split("\n")
    if lines[0] != '-----> Setting config vars':
        raise Exception(data)
    messages.success(request, 'Config updated')


def check_config_unset(request, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    lines = data.split("\n")
    if lines[0] != '-----> Unsetting ':
        regex = r"-----> Skipping ([a-zA-Z]*), it is not set in the environment"
        matches = re.finditer(regex, lines[0], re.MULTILINE)
        total_matches = sum(1 for _ in matches)
        if total_matches < 1:
            raise Exception(data)
    messages.success(request, 'Config updated')


def check_app_config_set(request, app_name, task_id):
    check_config_set(request, task_id)
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_global_config_set(request, app_name, task_id):
    check_config_set(request, task_id)
    clear_cache("config --global")
    return redirect(reverse('index'))


def check_app_config_unset(request, app_name, task_id):
    check_config_unset(request, task_id)
    clear_cache("config --global")
    return redirect(reverse('index'))


def format_config_string(data, splitter=":"):
    """
    Formats the config string submitted by the user to allow inserting multiple values in a single Dokku config:set use.
    The string is separated into pieces and then they respective key:value pairs are separated too.
    Then a new string is created in the format needed by Dokku command.
    Returns the formatted string like FOO=BAR LOREM=IPSUM (with trailing space on the end of string).
    """
    config_items = []
    cmd_string = ""
    original_items = data.split("\r\n")

    for item in original_items:
        splitted_input = item.split(splitter)
        if len(splitted_input) < 2:
            continue
        config_items.append(splitted_input)
        cmd_string += f"{splitted_input[0]}={splitted_input[1]} "

    return cmd_string


def global_config_bulk_set(request):
    """
    Inserts all the key:value items received in the submitted string.
    The string is formatted first in format_config_string function and after that passed to Dokku config:set command
    """
    form = forms.ConfigFormBulk(request.POST)

    if form.is_valid():
        cmd_string = format_config_string(form.cleaned_data['userInput'])

        if not cmd_string:
            raise Exception("The input is invalid")

        return run_cmd_with_log(
            None,
            "Setting global configuration",
            "config:set --global %s" % cmd_string,
            "check_global_config_set"
        )
    else:
        raise Exception("The submitted form is invalid")


def generic_list(app_name, data, name_field, fields, type_list=None):
    lines = data.split("\n")
    if lines[0].find("is not a dokku command") != -1:
        raise Exception("Need plugin!")
    if lines[0].find("There are no") != -1:
        return None
    fields = dict([[x, {}] for x in fields])
    last_field = None
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
    fields[last_field]["end"] = None
    results = []
    for line in lines[1:]:
        info = {}
        for f in fields.keys():
            if fields[f]["end"] is None:
                info[f] = line[fields[f]["start"]:].strip()
            else:
                info[f] = line[fields[f]["start"]:fields[f]["end"]].strip()
        results.append(info)

    items_names_list = []
    found_items = []

    for x in results:
        items_names_list.append(x[name_field])

    results = dict([[x[name_field], x] for x in results])

    if app_name in results:

        if type_list is None:
            return results[app_name]

        found_items.append(results[app_name])
        return found_items

    else:
        if type_list == "postgres":
            for postgres_name_item in items_names_list:
                if results[postgres_name_item]['LINKS'] == app_name:
                    found_items.append(results[postgres_name_item])
        elif type_list == "redis":
            for redis_name_item in items_names_list:
                if results[redis_name_item]['LINKS'] == app_name:
                    found_items.append(results[redis_name_item])
        elif type_list == "mariadb":
            for mariadb_name_item in items_names_list:
                if results[mariadb_name_item]['LINKS'] == app_name:
                    found_items.append(results[mariadb_name_item])

        if not found_items:
            return None
        else:
            return found_items


def db_list(app_name, data, type_list=None):
    return generic_list(app_name, data, "NAME", ["NAME", "VERSION", "STATUS", "EXPOSED PORTS", "LINKS"], type_list)


def buildpack_list(app_name):
    """
    Get a list of the configured buildpacks for an app.
    """
    data = run_cmd("buildpacks:list %s" % app_name)

    lines = data.split("\n")
    items = list()
    if lines[0].find("is not a dokku command") != -1:
        raise Exception("There is an error with the Dokku installation !")
    if lines[0].find("There are no") != -1:
        return None
    if lines[0].find('-----> %s buildpacks urls' % app_name) != -1:
        raise Exception("Buildpacks string not found")

    del lines[0]

    for line in lines:
        items.append(line.split()[0])

    return items


def postgres_list(app_name):
    data = run_cmd_with_cache("postgres:list")
    try:
        return db_list(app_name, data, 'postgres')
    except:
        clear_cache("postgres:list")
        raise


def redis_list(app_name):
    data = run_cmd_with_cache("redis:list")
    try:
        return db_list(app_name, data, 'redis')
    except:
        clear_cache("redis:list")
        raise


def mariadb_list(app_name):
    data = run_cmd_with_cache("mariadb:list")
    try:
        return db_list(app_name, data, 'mariadb')
    except:
        clear_cache("mariadb:list")
        raise


def letsencrypt(app_name):
    data = run_cmd_with_cache("letsencrypt:ls")
    return generic_list(app_name, data, "App name",
                        ["App name", "Certificate Expiry", "Time before expiry", "Time before renewal"])


def process_info(app_name):
    data = run_cmd_with_cache("ps:report %s" % app_name)
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


def domains_list(app_name):
    data = run_cmd_with_cache("domains:report %s" % app_name)
    vhosts = re.search("Domains app vhosts: (.*)", data)
    return [x.strip() for x in vhosts.groups()[0].split(" ") if x != ""]


@login_required(login_url='/accounts/login/')
def add_domain(request, app_name):
    form = forms.CreateDomainForm(request.POST)
    if form.is_valid():
        commands = ["domains:add %s %s" % (app_name, form.cleaned_data['name'])]
        if letsencrypt(app_name) != None:
            commands.append("letsencrypt %s" % app_name)
        return run_cmd_with_log(app_name, "Add domain %s" % form.cleaned_data['name'], commands, "check_domain")
    else:
        raise Exception


def check_domain(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Reloading nginx") != -1:
        clear_cache("domains:report %s" % app_name)
        messages.success(request, "Added domain name to %s" % app_name)
        return redirect(reverse('app_info', args=[app_name]))
    else:
        raise Exception(data)


@login_required(login_url='/accounts/login/')
def remove_domain(request, app_name):
    name = request.POST['name']
    commands = ["domains:remove %s %s" % (app_name, name)]
    if letsencrypt(app_name) != None:
        commands.append("letsencrypt %s" % app_name)
    return run_cmd_with_log(app_name, "Remove domain %s" % name, commands, "check_domain")


def remove_app_env_var(request, app_name):
    form = forms.ConfigRemoveForm(request.POST)

    if form.is_valid():
        return run_cmd_with_log(app_name,
                                "Removing app configuration",
                                "config:unset %s %s" % (app_name, form.cleaned_data['configKeyName']),
                                "check_app_config_unset")


@login_required(login_url='/accounts/login/')
def app_info(request, app_name):
    app, _ = models.App.objects.get_or_create(name=app_name)
    config = app_config(app_name)
    if "GITHUB_URL" in config:
        app.github_url = config["GITHUB_URL"]
        app.save()
    if request.method == 'POST':

        form = forms.ConfigFormBulk(request.POST)

        if form.is_valid():
            cmd_string = format_config_string(form.cleaned_data['userInput'])

            if not cmd_string:
                raise Exception("The input is invalid")

            return run_cmd_with_log(app_name,
                                    "Setting app configuration",
                                    "config:set %s %s" % (app_name, cmd_string),
                                    "check_app_config_set")
    else:
        form = forms.ConfigFormBulk()
    task_logs = models.TaskLog.objects.filter(app=app).order_by('when').all()

    return render(request, 'app_info.html', {
        'letsencrypt': letsencrypt(app_name),
        'process': process_info(app_name),
        'logs': ansi_escape.sub("", run_cmd("logs %s --num 100" % app_name)),
        'domains': domains_list(app_name),
        'domain_form': forms.CreateDomainForm(),
        'config_bulk_form': form,
        'app': app_name,
        'config': sorted(config.items()),
        'task_logs': task_logs,
    })


@login_required(login_url='/accounts/login/')
def deploy(request, app_name):
    if request.POST['action'] == "deploy":
        res = tasks.deploy.delay(app_name, request.POST['url'])
        clear_cache("config %s" % app_name)
        clear_cache("domains:report %s" % app_name)
        clear_cache("ps:report %s" % app_name)
        return redirect(
            reverse('wait_for_command', kwargs={'app_name': app_name, 'task_id': res.id, 'after': "check_deploy"}))
    elif request.POST['action'] == "rebuild":
        return run_cmd_with_log(app_name, "Rebuilding", "ps:rebuild %s" % app_name, "check_rebuild")
    else:
        raise Exception(request.POST['action'])


def create_postgres(request, app_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return run_cmd_with_log(app_name, "Add Postgres",
                            [
                                "postgres:create %s" % sanitized_link_name,
                                "postgres:link %s %s" % (sanitized_link_name, app_name)
                            ],
                            "check_postgres")


@login_required(login_url='/accounts/login/')
def remove_postgres(request, app_name, link_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return run_cmd_with_log(app_name, "Remove Postgres",
                            [
                                "postgres:unlink %s %s" % (sanitized_link_name, app_name),
                                "postgres:destroy %s -f" % sanitized_link_name
                            ],
                            "check_postgres_removal")


@login_required(login_url='/accounts/login/')
def create_redis(request, app_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return run_cmd_with_log(app_name, "Add Redis",
                            [
                                "redis:create %s" % sanitized_link_name,
                                "redis:link %s %s" % (sanitized_link_name, app_name)
                            ],
                            "check_redis")


@login_required(login_url='/accounts/login/')
def remove_redis(request, app_name, link_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return run_cmd_with_log(app_name, "Remove Redis",
                            [
                                "redis:unlink %s %s" % (sanitized_link_name, app_name),
                                "redis:destroy %s -f" % sanitized_link_name
                            ],
                            "check_redis_removal")


@login_required(login_url='/accounts/login/')
def create_mariadb(request, app_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return run_cmd_with_log(app_name, "Add MariaDB",
                            [
                                "mariadb:create %s" % sanitized_link_name,
                                "mariadb:link %s %s" % (sanitized_link_name, app_name)
                            ],
                            "check_mariadb")


@login_required(login_url='/accounts/login/')
def remove_mariadb(request, app_name, link_name):
    return run_cmd_with_log(app_name, "Remove MariaDB",
                            [
                                "mariadb:export %s" % link_name,
                                "mariadb:unlink %s %s" % (link_name, app_name),
                                "mariadb:destroy %s -f" % link_name
                            ],
                            "check_mariadb_removal")


@login_required(login_url='/accounts/login/')
def remove_buildpack(request, app_name):
    if request.method == 'POST':

        buildpack_form = forms.BuildpackRemoveForm(request.POST)

        if buildpack_form.is_valid():

            buildpack_url = buildpack_form.cleaned_data['buildpack_url']

            cmd = "buildpacks:remove %s %s" % (app_name, buildpack_url)

            return run_cmd_with_log(
                app_name,
                "Removing %s buildpack from %s" % (app_name, buildpack_url),
                [
                    cmd
                ],
                "check_buildpack_removal"
            )
        else:
            raise Exception("Cannot remove buildpack, the form is invalid.")


def add_buildpack(request, app_name):
    if request.method == 'POST':

        buildpack_form = forms.BuildpackAddForm(request.POST)

        if buildpack_form.is_valid():
            buildpack_url = buildpack_form.cleaned_data['buildpack_url']
            buildpack_type = "set" if buildpack_form.cleaned_data['buildpack_type'] is "set" else "add"

            cmd = "buildpacks:%s%s %s %s" % (
                buildpack_type,
                " --index %s" % buildpack_form.cleaned_data['buildpack_index'] if buildpack_form.cleaned_data[
                                                                                      'buildpack_index'] is not None else 1,
                app_name,
                buildpack_url
            )

            return run_cmd_with_log(
                app_name,
                "Setting buildpack to app" if buildpack_type is "set" else "Adding buildpack to list",
                [
                    cmd,
                ],
                'check_buildpack',
            )
        else:
            raise Exception("Cannot add buildpack, the form is invalid.")


def check_buildpack(request, app_name, task_id):
    clear_cache("builpacks:list %s" % app_name)
    messages.success(request, "Buildpack added to %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_deploy(request, app_name, task_id):
    clear_cache("config %s" % app_name)
    messages.success(request, "%s redeployed" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_rebuild(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Application deployed:") == -1:
        raise Exception(data)
    messages.success(request, "%s rebuilt" % app_name)
    clear_cache("config %s" % app_name)
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


def check_postgres_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Postgres container deleted") == -1:
        raise Exception(data)
    messages.success(request, "Postgres link removed from %s" % app_name)
    clear_cache("postgres:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_redis(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)

    sanitized_app_name = re.sub('[^A-Za-z0-9]+', '', app_name)

    if data.find("Redis container created") == -1 and \
            data.find("Redis service %s already exists" % sanitized_app_name) == -1:
        raise Exception(data)
    messages.success(request, "Redis added to %s" % app_name)
    clear_cache("redis:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_redis_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Redis container deleted") == -1:
        raise Exception(data)
    messages.success(request, "Redis link removed from %s" % app_name)
    clear_cache("redis:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_mariadb(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("MariaDB container created") == -1:
        raise Exception(data)
    messages.success(request, "MariaDB added to %s" % app_name)
    clear_cache("mariadb:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_mariadb_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("MariaDB container deleted") == -1:
        raise Exception(data)
    messages.success(request, "MariaDB link removed from %s" % app_name)
    clear_cache("mariadb:list")
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_buildpack_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)

    if data.find("-----> Removing") == -1:
        raise Exception(data)

    messages.success(request, "Buildpack removed from %s" % app_name)
    clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def create_app(app_name):
    models.App(name=app_name).save()
    return run_cmd_with_log(app_name, "Add app %s" % app_name, "apps:create %s" % app_name, "check_app")


def check_app(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = get_log(res)
    if data.find("Creating %s... done" % app_name) == -1:
        raise Exception(data)
    messages.success(request, "Created %s" % app_name)
    clear_cache("apps:list")
    return redirect(reverse('app_info', args=[app_name]))


@login_required(login_url='/accounts/login/')
def setup_letsencrypt(request, app_name):
    return run_cmd_with_log(app_name, "Enable Let's Encrypt", "letsencrypt %s" % app_name, "check_letsencrypt")


def check_letsencrypt(request, app_name, task_id):
    res = AsyncResult(task_id)
    log = get_log(res)
    if log.find("Certificate retrieved successfully") != -1:
        clear_cache("letsencrypt:ls")
        return redirect(reverse('app_info', args=[app_name]))
    else:
        return render(request, 'command_wait.html',
                      {'app': app_name, 'task_id': task_id, 'log': log, 'state': res.state,
                       'running': res.state in [state(PENDING), state(STARTED)]})


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
    apps = models.App.objects.filter(github_url=clone_url)
    if not apps.exists():
        return HttpResponseBadRequest("Can't find an entry for clone URL %s" % clone_url)
    app = apps.first()
    res = tasks.deploy.delay(app.name, clone_url)
    clear_cache("config %s" % app.name)
    return HttpResponse("Running deploy. Deploy log is at %s" % request.build_absolute_uri(
        reverse('show_log', kwargs={'task_id': res.id})))


@timeout_decorator.timeout(5, use_signals=False)
def check_status():
    # Clearing the cache and then trying a command makes sure that
    # - The cache is up
    # - Celery is up
    # - We can run dokku commands
    clear_cache("config --global")
    run_cmd_with_cache("config --global")


def status(request):
    try:
        check_status()
        return HttpResponse("All good")
    except timeout_decorator.TimeoutError:
        return HttpResponseServerError("Timeout trying to get status")
