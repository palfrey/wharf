from typing import Callable, Iterator, cast
from django.conf import LazySettings
from django.core.cache.backends.locmem import LocMemCache
import pytest
from django.core.cache import cache

MULTIPLE_COMMANDS = ["delete_many"]

class RecordingCache(LocMemCache):
    actions = []
    # Some commands e.g. delete_many are implemented via other commands
    # Don't record the internal details
    _pause_internal = False

    def _make_internal(self, entry):
        def internal(*args, **kwargs):
            if not self._pause_internal:
                item = [entry]
                if args != ():
                    item.append(args)
                if kwargs != {}:
                    item.append(kwargs)
                if len(item) == 1:
                    self.actions.append(item[0])
                else:
                    self.actions.append(tuple(item))
            if entry in MULTIPLE_COMMANDS:
                self._pause_internal = True
            ret = self._originals[entry](*args, **kwargs)
            if entry in MULTIPLE_COMMANDS:
                self._pause_internal = False
            return ret
        return internal

    def __init__(self, *args, **kwargs):
        LocMemCache.__init__(self, *args, **kwargs)
        self._originals = {}
        for entry in dir(self):
            if entry.startswith("_") or entry in ["actions", "key_func", "make_key", "make_and_validate_key", "validate_key"]:
                continue
            self._originals[entry] = getattr(self, entry)
            if not isinstance(self._originals[entry], Callable):
                continue
            
            setattr(self, entry, self._make_internal(entry))


@pytest.fixture
def recording_cache(settings: LazySettings) -> Iterator[RecordingCache]:
    settings.CACHES["default"] = {
        "BACKEND": "tests.recording_cache.RecordingCache",
        "LOCATION": "unique-snowflake",
    }
    recording_cache = cast(RecordingCache, cache)
    yield recording_cache
    recording_cache.actions = []