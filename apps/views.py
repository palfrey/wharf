from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, reverse
from celery.states import state, FAILURE, SUCCESS, PENDING, STARTED
from datetime import datetime

import re

import wharf.tasks as tasks
from .models import TaskLog, App
from .forms import ConfigFormBulk, CreateDomainForm, CreateAppForm, ConfigForm
from .helpers import config as configuration, commands, buildpacks, postgres, mariadb, redis, letsencrypt, domains, apps, utils, cache

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
            'process': apps.process_info(app_name),
            'logs': apps.ansi_escape.sub("", commands.run_cmd("logs %s --num 100" % app_name)),
            'domains': domains.domains_list(app_name),
            'domain_form': CreateDomainForm(),
            'config_bulk_form': form,
            'app': app_name,
            'git_url': config.get('GITHUB_URL', None),
            'config': sorted(config.items()),
            'task_logs': TaskLog.objects.filter(app=app).order_by('-when').all(),
        }
    )


@login_required(login_url='/accounts/login/')
def index(request):
    try:
        apps_list = apps.app_list()
    except Exception as e:
        if e.__class__.__name__ in ["AuthenticationException"]:  # Can't use class directly as Celery mangles things
            return render(request, 'setup_key.html', {'key': tasks.get_public_key.delay().get()})
        else:
            raise
    if request.method == 'POST':
        app_form = CreateAppForm(request.POST)
        if app_form.is_valid():
            return apps.create_app(app_form.cleaned_data['name'])
    else:
        app_form = CreateAppForm()
    config_form = ConfigForm()
    config_bulk_form = ConfigFormBulk()
    config = configuration.global_config()
    return render(
        request,
        'list_apps.html',
        {
            'apps': apps_list,
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
    log = apps.ansi_escape.sub("", utils.get_log(res))
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


@login_required(login_url='/accounts/login/')
def wait_for_command(request, app_name, task_id, after):
    res = AsyncResult(task_id)
    if app_name != '_':
        app = App.objects.get(name=app_name)
        task, created = TaskLog.objects.get_or_create(
            task_id=task_id,
            defaults={'app': app, 'when': datetime.now()}
        )
        description = task.description
    else:
        description = ""
    if res.state == state(SUCCESS):
        return redirect(
            reverse(
                after,
                kwargs={
                    'app_name': app_name,
                    'task_id': task_id
                }
            )
        )
    log = ansi_escape.sub("", utils.get_log(res))
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
def check_letsencrypt(request, app_name, task_id):
    res = AsyncResult(task_id)
    log = utils.get_log(res)
    if log.find("Certificate retrieved successfully") != -1:
        cache.clear_cache("letsencrypt:ls")
        return redirect(reverse('app_info', args=[app_name]))
    else:
        return render(
            request,
            'command_wait.html',
            {
                'app': app_name,
                'task_id': task_id,
                'log': log,
                'state': res.state,
                'running': res.state in [state(PENDING), state(STARTED)]
            }
        )