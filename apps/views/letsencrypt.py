from . import commands, utils, cache
from celery.result import AsyncResult
from celery.states import state, PENDING, STARTED
from django.shortcuts import redirect, reverse, render
from django.contrib.auth.decorators import login_required


def letsencrypt(app_name):
    data = commands.run_cmd_with_cache("letsencrypt:ls")
    return utils.generic_list(
        app_name,
        data,
        "App name",
        ["App name", "Certificate Expiry", "Time before expiry", "Time before renewal"]
    )


def setup_letsencrypt(request, app_name):
    return commands.run_cmd_with_log(
        app_name,
        "Enable Let's Encrypt",
        "letsencrypt %s" % app_name,
        "check_letsencrypt"
    )


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