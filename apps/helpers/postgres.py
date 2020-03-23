from . import commands, utils, cache
from celery.result import AsyncResult
from django.contrib import messages
from django.shortcuts import redirect, reverse

import re


def postgres_list(app_name):
    data = commands.run_cmd_with_cache("postgres:list")
    try:
        return utils.db_list(
            app_name,
            data,
            "postgres"
        )
    except (Exception, RuntimeError):
        cache.clear_cache("postgres:list")
        raise


def create_postgres(request, app_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return commands.run_cmd_with_log(
        app_name,
        "Add Postgres",
        [
            "postgres:create %s" % sanitized_link_name,
            "postgres:link %s %s" % (sanitized_link_name, app_name)
        ],
        "check_postgres"
    )


def remove_postgres(request, app_name, link_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return commands.run_cmd_with_log(
        app_name,
        "Remove Postgres",
        [
            "postgres:unlink %s %s" % (sanitized_link_name, app_name),
            "postgres:destroy %s -f" % sanitized_link_name
        ],
        "check_postgres_removal"
    )


def check_postgres(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("Postgres container created") == -1:
        raise Exception(data)
    messages.success(request, "Postgres added to %s" % app_name)
    cache.clear_cache("postgres:list")
    cache.clear_cache("config %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )


def check_postgres_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("Postgres container deleted") == -1:
        raise Exception(data)
    messages.success(request, "Postgres link removed from %s" % app_name)
    cache.clear_cache("postgres:list")
    cache.clear_cache("config %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )
