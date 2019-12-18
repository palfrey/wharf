from . import commands, utils, cache
from celery.result import AsyncResult
from django.contrib import messages
from django.shortcuts import redirect, reverse

import re


def mariadb_list(app_name):
    data = commands.run_cmd_with_cache("mariadb:list")
    try:
        return utils.db_list(
            app_name,
            data,
            "mariadb"
        )
    except (Exception, RuntimeError):
        cache.clear_cache("mariadb:list")
        raise


def create_mariadb(request, app_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return commands.run_cmd_with_log(
        app_name,
        "Add MariaDB",
        [
            "mariadb:create %s" % sanitized_link_name,
            "mariadb:link %s %s" % (sanitized_link_name, app_name)
        ],
        "check_mariadb"
    )


def remove_mariadb(request, app_name, link_name):
    return commands.run_cmd_with_log(
        app_name,
        "Remove MariaDB",
        [
            "mariadb:unlink %s %s" % (link_name, app_name),
            "mariadb:destroy %s -f" % link_name
        ],
        "check_mariadb_removal"
    )


def check_mariadb(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("MariaDB container created") == -1:
        raise Exception(data)
    messages.success(request, "MariaDB added to %s" % app_name)
    cache.clear_cache("mariadb:list")
    cache.clear_cache("config %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )


def check_mariadb_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("MariaDB container deleted") == -1:
        raise Exception(data)
    messages.success(request, "MariaDB link removed from %s" % app_name)
    cache.clear_cache("mariadb:list")
    cache.clear_cache("config %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )
