from . import commands, utils


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
