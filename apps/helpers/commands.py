from datetime import datetime
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render, redirect, reverse

from ..models import App, TaskLog

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
