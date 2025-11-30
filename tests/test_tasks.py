import subprocess
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest
from redis import StrictRedis

import wharf.tasks as tasks
from apps import models

root_path = Path(__file__).parent.parent
test_app_path = root_path.joinpath("repos", "test_app")

processes = [
    ["git", "clone", "git://foo", test_app_path.as_posix()],
    ["git", "pull"],
    ["git", "push", "-f", "dokku", "master"],
    ["git", "push", "-f", "dokku", "main"],
]


def custom_mock_processes(override_commands: list[list[str]]) -> Callable:
    def _internal(task_name, args, **kwargs):
        if args in override_commands:
            raise Exception("override")
        if args in processes:
            return
        print(args)
        raise Exception(args)

    return _internal


mock_processes = custom_mock_processes([])


@pytest.mark.django_db
@patch("wharf.tasks.run_process")
@pytest.mark.parametrize("branch", ["main", "master"])
def test_deploy(
    patched_runprocess: MagicMock, branch: str, monkeypatch: pytest.MonkeyPatch
):
    patched_runprocess.side_effect = mock_processes
    monkeypatch.setattr(StrictRedis, "append", lambda _self, _key, _value: b"")
    models.App.objects.create(name="test_app")
    if test_app_path.exists():
        subprocess.check_call(["rm", "-Rf", test_app_path.as_posix()])
    test_app_path.mkdir()
    subprocess.check_call(["git", "init"], cwd=test_app_path)

    tasks.deploy("test_app", "git://foo", branch)  # pyright: ignore[reportCallIssue]


def test_handle_data_non_utf8(monkeypatch: pytest.MonkeyPatch):
    redis_keys = []

    def store_value(_self, key, value):
        nonlocal redis_keys
        redis_keys.append((key, value))

    monkeypatch.setattr(StrictRedis, "append", store_value)
    tasks.handle_data("abc", "æ".encode("cp1252"))

    assert redis_keys == [("abc", "\ufffd")]
