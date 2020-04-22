from . import commands, utils, cache
from ..forms import ConfigFormBulk
from celery.result import AsyncResult
from django.contrib import messages
from django.shortcuts import redirect, reverse


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
    data = commands.run_cmd_with_cache("config %s" % app_name)
    return generic_config(app_name, data)


def global_config():
    data = commands.run_cmd_with_cache("config --global")
    return generic_config("global", data)


def check_config_set(request, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    lines = data.split("\n")
    if lines[0] != '-----> Setting config vars':
        raise Exception(data)
    messages.success(request, 'Config updated')


def check_global_config_set(request, app_name, task_id):
    check_config_set(request, task_id)
    cache.clear_cache("config --global")
    return redirect(reverse('index'))


def check_app_config_set(request, app_name, task_id):
    check_config_set(request, task_id)
    cache.clear_cache("config %s" % app_name)
    return redirect(reverse('app_info', args=[app_name]))


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
    form = ConfigFormBulk(request.POST)

    if form.is_valid():
        cmd_string = format_config_string(form.cleaned_data['userInput'])

        if not cmd_string:
            raise Exception("The input is invalid")

        return commands.run_cmd_with_log(
            None,
            "Setting global configuration",
            "config:set --global %s" % cmd_string,
            "check_global_config_set"
        )
    else:
        raise Exception("The submitted form is invalid")
