from . import commands, utils, cache
from celery.result import AsyncResult
from django.contrib import messages
from django.shortcuts import redirect, reverse

import re


def redis_list(app_name):
    data = commands.run_cmd_with_cache("redis:list")
    try:
        return utils.db_list(
            app_name,
            data,
            "redis"
        )
    except (Exception, RuntimeError):
        cache.clear_cache("redis:list")
        raise


def create_redis(request, app_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return commands.run_cmd_with_log(
        app_name,
        "Add Redis",
        [
            "redis:create %s" % sanitized_link_name,
            "redis:link %s %s" % (sanitized_link_name, app_name)
        ],
        "check_redis"
    )


def remove_redis(request, app_name, link_name):
    sanitized_link_name = re.sub('[^A-Za-z0-9]+', '', app_name)
    return commands.run_cmd_with_log(
        app_name,
        "Remove Redis",
        [
            "redis:unlink %s %s" % (sanitized_link_name, app_name),
            "redis:destroy %s -f" % sanitized_link_name
        ],
        "check_redis_removal"
    )


def check_redis(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)

    sanitized_app_name = re.sub('[^A-Za-z0-9]+', '', app_name)

    if data.find("Redis container created") == -1 and \
            data.find("Redis service %s already exists" % sanitized_app_name) == -1:
        raise Exception(data)

    messages.success(request, "Redis added to %s" % app_name)
    cache.clear_cache("redis:list")
    cache.clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


def check_redis_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("Redis container deleted") == -1:
        raise Exception(data)
    messages.success(request, "Redis link removed from %s" % app_name)
    cache.clear_cache("redis:list")
    cache.clear_cache("config %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )
