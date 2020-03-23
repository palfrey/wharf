from celery.states import state, PENDING
from redis import StrictRedis
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import redirect, reverse
from . import cache as cache_helper, commands

import wharf.tasks as tasks
import timeout_decorator

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)


def get_log(res):
    key = tasks.task_key(res.id)
    if res.state > state(PENDING):
        raw = redis.get(key)
        if raw is None:
            return ""
        return raw.decode('utf-8')
    else:
        return ""


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
    return generic_list(
        app_name,
        data,
        "NAME",
        ["NAME", "VERSION", "STATUS", "EXPOSED PORTS", "LINKS"],
        type_list
    )


def refresh_all(request):
    cache.clear()
    return redirect(reverse('index'))


@timeout_decorator.timeout(5, use_signals=False)
def check_status():
    # Clearing the cache and then trying a command makes sure that
    # - The cache is up
    # - Celery is up
    # - We can run dokku commands
    cache_helper.clear_cache("config --global")
    commands.run_cmd_with_cache("config --global")


def status(request):
    try:
        check_status()
        return HttpResponse("All good")
    except timeout_decorator.TimeoutError:
        return HttpResponseServerError("Timeout trying to get status")