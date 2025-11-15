import os

os.environ["REDIS_URL"] = "redis://redis:6379/1"

from wharf.settings import *  # noqa: F403

CACHES = {
    # "default": {
    #     "BACKEND": "tests.recording_cache.RecordingCache",
    #     "LOCATION": "unique-snowflake",
    # }
}
