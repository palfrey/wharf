from unittest.mock import MagicMock, patch

from django.http import HttpRequest
import pytest
from apps.views import app_list, check_app
from celery.result import AsyncResult
from celery.states import state, PENDING, SUCCESS, FAILURE, STARTED
from redis import StrictRedis

class MockCelery:
    def __init__(self, res: str):
        self.res = res

    def get(self):
        return self.res
    
commands = {
    ("apps:list", ): """=====> My Apps
wharf"""
}

def mock_commands(*args):
    if args in commands:
        return MockCelery(commands[args])
    print(args)
    raise Exception

@pytest.fixture
def mock_request() -> HttpRequest:
    mr = MagicMock(spec=HttpRequest)
    mr.META = MagicMock()
    mr._messages = MagicMock()
    return mr

@patch("wharf.tasks.run_ssh_command.delay")
def test_app_list(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    assert app_list() == ["wharf"]

@patch("wharf.tasks.run_ssh_command.delay")
def test_check_app(patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(AsyncResult, "state", state(SUCCESS))
    monkeypatch.setattr(StrictRedis, "get", lambda _self, _key: b"""Creating 3b56c612721a4b88a6fece5d67aa90a3...
-----> Creating new app virtual host file...""")

    patched_delay.side_effect = mock_commands
    resp = check_app(mock_request, "3b56c612721a4b88a6fece5d67aa90a3", "1234")
    assert resp.status_code == 302, resp
    assert resp.url == "/apps/3b56c612721a4b88a6fece5d67aa90a3"