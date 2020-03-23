from . import commands
from django.core.cache import cache


def clear_cache(cmd):
    key = commands.cmd_key(cmd)
    cache.delete(key)

