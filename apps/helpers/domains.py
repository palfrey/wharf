from . import commands, utils, cache, letsencrypt
from celery.result import AsyncResult
from django.contrib import messages
from django.shortcuts import redirect, reverse
from ..forms import CreateDomainForm

import re


def domains_list(app_name):
    data = commands.run_cmd_with_cache("domains:report %s" % app_name)
    v_hosts = re.search("Domains app vhosts: (.*)", data)
    return [x.strip() for x in v_hosts.groups()[0].split(" ") if x != ""]


def add_domain(request, app_name):
    form = CreateDomainForm(request.POST)
    if form.is_valid():
        cmd = ["domains:add %s %s" % (app_name, form.cleaned_data['name'])]
        if letsencrypt.letsencrypt(app_name) is not None:
            cmd.append("letsencrypt %s" % app_name)
        return commands.run_cmd_with_log(
            app_name,
            "Add domain %s" % form.cleaned_data['name'],
            cmd,
            "check_domain"
        )
    else:
        raise Exception("Cannot add domain, the form is invalid.")


def check_domain(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)
    if data.find("Reloading nginx") != -1:
        cache.clear_cache("domains:report %s" % app_name)
        messages.success(request, "Added domain name to %s" % app_name)
        return redirect(
            reverse(
                'app_info',
                args=[app_name]
            )
        )
    else:
        raise Exception(data)


def remove_domain(request, app_name):
    name = request.POST['name']
    cmd = ["domains:remove %s %s" % (app_name, name)]
    if letsencrypt.letsencrypt(app_name) is not None:
        cmd.append("letsencrypt %s" % app_name)
    return commands.run_cmd_with_log(
        app_name,
        "Remove domain %s" % name,
        cmd,
        "check_domain"
    )
