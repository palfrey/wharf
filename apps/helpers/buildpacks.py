from . import commands, utils, cache
from celery.result import AsyncResult
from django.contrib import messages
from django.shortcuts import redirect, reverse
from ..forms import BuildpackAddForm, BuildpackRemoveForm


def buildpack_list(app_name):
    """
    Get a list of the configured buildpacks for an app.
    """
    data = commands.run_cmd("buildpacks:list %s" % app_name)

    lines = data.split("\n")
    items = list()
    if lines[0].find("is not a dokku command") != -1:
        raise Exception("There is an error with the Dokku installation !")
    if lines[0].find("There are no") != -1:
        return None
    if lines[0].find('-----> %s buildpacks urls' % app_name) != -1:
        raise Exception("Buildpacks string not found")

    del lines[0]

    for line in lines:
        items.append(line.split()[0])

    return items


def add_buildpack(request, app_name):

    if request.method == 'POST':

        buildpack_form = BuildpackAddForm(request.POST)

        if buildpack_form.is_valid():
            buildpack_url = buildpack_form.cleaned_data['buildpack_url']
            buildpack_type = "set" if buildpack_form.cleaned_data['buildpack_type'] is "set" else "add"

            cmd = "buildpacks:%s%s %s %s" % (
                buildpack_type,
                " --index %s" % buildpack_form.cleaned_data['buildpack_index'] if buildpack_form.cleaned_data['buildpack_index'] is not None else 1,
                app_name,
                buildpack_url
            )

            return commands.run_cmd_with_log(
                app_name,
                "Setting buildpack to app" if buildpack_type is "set" else "Adding buildpack to list",
                [
                    cmd,
                ],
                'check_buildpack',
            )
        else:
            raise Exception("Cannot add buildpack, the form is invalid.")


def remove_buildpack(request, app_name):

    if request.method == 'POST':

        buildpack_form = BuildpackRemoveForm(request.POST)

        if buildpack_form.is_valid():

            buildpack_url = buildpack_form.cleaned_data['buildpack_url']

            cmd = "buildpacks:remove %s %s" % (app_name, buildpack_url)

            return commands.run_cmd_with_log(
                app_name,
                "Removing %s buildpack from %s" % (app_name, buildpack_url),
                [
                    cmd
                ],
                "check_buildpack_removal"
            )
        else:
            raise Exception("Cannot remove buildpack, the form is invalid.")


def check_buildpack(request, app_name, task_id):
    cache.clear_cache("builpacks:list %s" % app_name)
    messages.success(request, "Buildpack added to %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )


def check_buildpack_removal(request, app_name, task_id):
    res = AsyncResult(task_id)
    data = utils.get_log(res)

    if data.find("-----> Removing") == -1:
        raise Exception(data)

    messages.success(request, "Buildpack removed from %s" % app_name)
    cache.clear_cache("config %s" % app_name)
    return redirect(
        reverse(
            'app_info',
            args=[app_name]
        )
    )
