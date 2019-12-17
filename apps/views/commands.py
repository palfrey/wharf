from celery.result import AsyncResult
from celery.states import state, PENDING, SUCCESS, FAILURE, STARTED

from datetime import datetime
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render, redirect, reverse
from django.contrib.auth.decorators import login_required

from ..models import App, TaskLog
from . import utils

import re
import wharf.tasks as tasks

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
    cache.set(key, res, settings.GLOBAL_COMMAND_CACHE_EXPIRATION)
    return res


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


def run_cmd_with_log(app_name, description, cmd, after):
    res = tasks.run_ssh_command.delay(cmd)
    if app_name is None:
        app_name = '_'
    else:
        TaskLog(
            task_id=res.id,
            when=datetime.now(),
            app=App.objects.get(name=app_name),
            description=description
        ).save()

    return redirect(
        reverse(
            'wait_for_command',
            kwargs={
                'app_name': app_name,
                'task_id': res.id,
                'after': after
            }
        )
    )
