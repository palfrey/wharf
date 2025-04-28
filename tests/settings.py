import os

os.environ["REDIS_URL"] = "redis://redis:6379/1"

from wharf.settings import *

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}