import re
import uuid
from pathlib import Path
from typing import Any, Callable, cast
from unittest.mock import MagicMock, Mock, patch

import pytest
from celery.result import AsyncResult
from celery.states import SUCCESS, state
from django.conf import LazySettings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.test import Client
from model_bakery import baker
from redis import StrictRedis

from apps import models
from apps.views import (
    actions,
    app_config_delete,
    app_info,
    app_list,
    check_app,
    check_app_config_delete,
    check_letsencrypt,
    check_postgres,
    check_redis,
    check_remove_letsencrypt,
    check_remove_postgres,
    check_remove_redis,
    check_rename_app,
    config,
    create_app,
    create_postgres,
    create_redis,
    databases,
    domains,
    global_config,
    index,
    letsencrypt,
    logs,
    process_info,
    refresh,
    refresh_all,
    remove_letsencrypt,
    remove_postgres,
    remove_redis,
    rename_app,
    setup_letsencrypt,
)
from tests.recording_cache import RecordingCache


class MockCelery:
    def __init__(self, res: object):
        self.res = res
        self.id = uuid.uuid4()

    def get(self):
        return self.res


commands = {
    ("apps:list",): """=====> My Apps
wharf""",
    ("config:show test_app",): """=====> test_app env vars
DOKKU_APP_RESTORE:  1
DOKKU_APP_TYPE:     dockerfile
DOKKU_PROXY_PORT:   80""",
    ("config:show missing",): " !     App missing does not exist",
    ("postgres:list",): """=====> Postgres services
wharf""",
    ("postgres:info test_app",): """=====> test_app postgres service information
       Config dir:          /var/lib/dokku/services/postgres/test_app/data
       Config options:
       Data dir:            /var/lib/dokku/services/postgres/test_app/data
       Dsn:                 postgres://postgres:aa23a509ff7443011ebfa49e3c3a582a@dokku-postgres-test_app:5432/test_app
       Exposed ports:       -
       Id:                  3a07c995d32e13766d3ebc44d040391f434e234d3d9c6021410eff4a130af656
       Internal ip:         172.17.0.3
       Initial network:
       Links:               wharf
       Post create network:
       Post start network:
       Service root:        /var/lib/dokku/services/postgres/test_app
       Status:              running
       Version:             postgres:17.4""",
    ("redis:info test_app",): """=====> test_app redis service information
       Config dir:          /var/lib/dokku/services/redis/test_app/config
       Config options:
       Data dir:            /var/lib/dokku/services/redis/test_app/data
       Dsn:                 redis://:6654f1fd4527260516b99ea515f5d283e9ab887822f7e3c9d5d37ac4815b73d2@dokku-redis-wharf:6379
       Exposed ports:       -
       Id:                  12d11c44ecb0f75175ab4c15a853d9b2801d1349f5ff16610dadf154184256d7
       Internal ip:         172.17.0.2
       Initial network:
       Links:               test_app
       Post create network:
       Post start network:
       Service root:        /var/lib/dokku/services/redis/test_app
       Status:              running
       Version:             redis:7.4.2""",
    ("ps:report test_app",): """=====> test_app ps information
       Deployed:                      true
       Processes:                     2
       Ps can scale:                  true
       Ps computed procfile path:     Procfile
       Ps global procfile path:       Procfile
       Ps procfile path:
       Ps restart policy:             on-failure:10
       Restore:                       true
       Running:                       true
       Status celery 1:               running (CID: 68b2897a761)
       Status web 1:                  running (CID: d536b673b49)""",
    (
        "logs test_app --num 100",
    ): """2025-04-25T23:07:53.894820268Z app[celery.1]: System check identified some issues:
2025-04-25T23:07:53.895026545Z app[celery.1]:
2025-04-25T23:07:53.895030874Z app[celery.1]: WARNINGS:""",
    ("domains:report test_app",): """"=====> test_app domains information
       Domains app enabled:           true
       Domains app vhosts:            test_app.vagrant
       Domains global enabled:        true
       Domains global vhosts:         vagrant""",
    ("postgres:info missing",): " !     Postgres service missing does not exist",
    ("redis:info missing",): " !     Redis service missing does not exist",
    (
        "letsencrypt:ls",
    ): "-----> App name  Certificate Expiry        Time before expiry        Time before renewal",
    (
        "letsencrypt:list",
    ): "-----> App name  Certificate Expiry        Time before expiry        Time before renewal",
    ("ps:report missing",): " !     App missing does not exist",
    ("logs missing --num 100",): " !     App missing does not exist",
    ("domains:report missing",): " !     App missing does not exist",
    (
        "plugin:list",
    ): """ letsencrypt          0.9.4 enabled    Automated installation of let's encrypt TLS certificates
  logs                 0.35.18 enabled    dokku core logs plugin
  network              0.35.18 enabled    dokku core network plugin""",
    ("apps:create foo",): "",
    ("config:show --global",): """=====> global env vars
CURL_CONNECT_TIMEOUT:  90
CURL_TIMEOUT:          600""",
    ("postgres:create foo",): """Waiting for container to be ready
       Creating container database
       Securing connection to database
=====> Postgres container created: foo""",
    ("postgres:link foo foo",): """-----> Setting config vars
       DATABASE_URL:  postgres://postgres:2a871f1589b4519719428602980939bb@dokku-postgres-foo:5432/foo""",
    ("postgres:unlink foo foo",): "-----> Unsetting DATABASE_URL",
    ("postgres:destroy foo --force",): """=====> Pausing container
       Container paused
       Removing container
       Removing data
=====> Postgres container deleted: foo""",
    (
        "ps:report non-running-app",
    ): """No such object: cdbd631f11431826fb7ccfd257921e6b0ac1e6fc7986948e44e0d49609e11123
=====> non-running-app ps information
        Deployed:                      true
        Processes:                     1
        Ps can scale:                  true
        Ps computed procfile path:     Procfile
        Ps global procfile path:       Procfile
        Ps procfile path:
        Ps restart policy:             on-failure:10
        Restore:                       true
        Running:                       false
        Status web 1:                  missing (CID: cdbd631f114)""",
    ("redis:create foo",): """       Waiting for container to be ready
=====> Redis container created: foo
=====> foo redis service information
       Config dir:          /var/lib/dokku/services/redis/foo/config
       Config options:
       Data dir:            /var/lib/dokku/services/redis/foo/data
       Dsn:                 redis://:584fb7aa7ca03acda2bc8c81c056ac81e0ec59d10efec8137cfcf893854f5570@dokku-redis-foo:6379
       Exposed ports:       -
       Id:                  37f96e39797e4a731d750a19ae0e3255fb84fede13d1e704ae61d18ac037e4ad
       Internal ip:         172.17.0.4
       Initial network:
       Links:               -
       Post create network:
       Post start network:
       Service root:        /var/lib/dokku/services/redis/foo
       Status:              running
       Version:             redis:8.4.0""",
    ("redis:link foo foo",): """----> Setting config vars
       REDIS_URL:  redis://:584fb7aa7ca03acda2bc8c81c056ac81e0ec59d10efec8137cfcf893854f5570@dokku-redis-foo:6379""",
    ("redis:unlink foo foo",): """-----> Unsetting REDIS_URL""",
    ("redis:destroy foo --force",): """=====> Deleting foo
=====> Pausing container
       Container paused
       Removing container
       Removing data
=====> Redis container deleted: foo""",
    (
        "letsencrypt:set test_app email foo@bar.com",
    ): "=====> Setting email to foo@bar.com",
    ("letsencrypt:enable test_app",): """=====> Enabling letsencrypt for test_app
-----> Enabling ACME proxy for test_app...
-----> Getting letsencrypt certificate for test_app via HTTP-01
        - Domain 'test_app.vagrant'
2025/12/20 21:38:20 No key found for account foo@bar.com. Generating a P256 key.
2025/12/20 21:38:20 Saved key to /certs/accounts/acme-v02.api.letsencrypt.org/foo@bar.com/keys/foo@bar.com.key
2025/12/20 21:38:20 [INFO] acme: Registering account for foo@bar.com
2025/12/20 21:38:20 [INFO] [test_app.vagrant] acme: Obtaining bundled SAN certificate
       !!!! HEADS UP !!!!

       Your account credentials have been saved in your Let's Encrypt
       configuration directory at "/certs/accounts".

       You should make a secure backup of this folder now. This
       configuration directory will also contain certificates and
       private keys obtained from Let's Encrypt so making regular
       backups of this folder is ideal.
2025/12/20 21:38:21 [INFO] [test_app.vagrant] AuthURL: https://acme-v02.api.letsencrypt.org/acme/authz/12345/6789
2025/12/20 21:38:21 [INFO] [test_app.vagrant] acme: Could not find solver for: tls-alpn-01
2025/12/20 21:38:21 [INFO] [test_app.vagrant] acme: use http-01 solver
2025/12/20 21:38:21 [INFO] [test_app.vagrant] acme: Trying to solve HTTP-01
2025/12/20 21:38:29 [INFO] [test_app.vagrant] The server validated our request
2025/12/20 21:38:29 [INFO] [test_app.vagrant] acme: Validations succeeded; requesting certificates
2025/12/20 21:38:29 [INFO] [test_app.vagrant] Server responded with a certificate.
-----> Certificate retrieved successfully.
-----> Installing let's encrypt certificates
-----> Unsetting DOKKU_PROXY_PORT
-----> Setting config vars
       DOKKU_PROXY_PORT_MAP:  http:80:5000
-----> Setting config vars
       DOKKU_PROXY_PORT_MAP:  http:80:5000 https:443:5000
-----> Configuring test_app.vagrant...(using built-in template)
-----> Creating https nginx.conf
       Enabling HSTS
       Reloading nginx
-----> Ensuring network configuration is in sync for test_app
-----> Configuring test_app.vagrant...(using built-in template)
-----> Creating https nginx.conf
       Enabling HSTS
       Reloading nginx
-----> Disabling ACME proxy for test_app...
-----> Done""",
    ("letsencrypt:disable test_app --force",): """-----> Disabling letsencrypt for app
       Removing letsencrypt files for test_app
       Removing SSL endpoint from test_app
-----> Unsetting DOKKU_PROXY_SSL_PORT
-----> Setting config vars
       DOKKU_PROXY_PORT_MAP:  http:80:5000
-----> Configuring test_app.vagrant...(using built-in template)
-----> Creating http nginx.conf
       Reloading nginx
-----> Done""",
    ("config:unset test_app FOO_KEY",): """-----> Unsetting FOO_KEY""",
    ("apps:rename test_app bar",): """-----> Renaming test_app to bar
-----> Creating bar...
-----> Creating new app virtual host file...
-----> Destroying test_app (including all add-ons)
       Unlinking from wharf
       Unlinking from wharf
-----> Updated schedule file
-----> Updated schedule file
Warning: The unit file, source configuration file or drop-ins of nginx.service changed on disk. Run 'systemctl daemon-reload' to reload units.
                                                                                                                                              -----> Cleaning up...
-----> Retiring old containers and images""",
}


def custom_mock_commands(override_commands: dict[Any, str]) -> Callable:
    def _internal(*args):
        if type(args[0]) is list:
            all_celerys = [_internal(x) for x in args[0]]
            return MockCelery("\n".join([c.res for c in all_celerys]))
        if args in override_commands:
            return MockCelery(override_commands[args])
        if args in commands:
            return MockCelery(commands[args])
        print(args)
        raise Exception(args)

    return _internal


mock_commands = custom_mock_commands({})


@pytest.fixture
def mock_request() -> HttpRequest:
    mr = MagicMock(spec=HttpRequest)
    mr.META = MagicMock()
    mr._messages = MagicMock()
    mr.method = MagicMock()
    return mr


@pytest.fixture(autouse=True)
def disable_cache(
    monkeypatch: pytest.MonkeyPatch,
    recording_cache: RecordingCache,
):
    monkeypatch.setattr(cache, "set", lambda _key, _value, _timeout: None)


@pytest.fixture(autouse=True)
def patch_csrf_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "django.middleware.csrf.get_token", Mock(return_value="predictabletoken")
    )
    yield


@patch("wharf.tasks.run_ssh_command.delay")
def test_app_list(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    assert app_list() == ["wharf"]


def finished_log(monkeypatch: pytest.MonkeyPatch, contents: str):
    monkeypatch.setattr(AsyncResult, "state", state(SUCCESS))
    monkeypatch.setattr(
        StrictRedis,
        "get",
        lambda _self, _key: contents.encode("utf-8"),
    )


@patch("wharf.tasks.run_ssh_command.delay")
def test_check_app(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    finished_log(
        monkeypatch,
        """Creating test_app...
-----> Creating new app virtual host file...""",
    )

    patched_delay.side_effect = mock_commands
    resp = check_app(mock_request, "test_app", "1234")
    assert resp.status_code == 302, resp
    assert resp.url == "/apps/test_app"


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_app_info(patched_delay: MagicMock, mock_request: HttpRequest):
    patched_delay.side_effect = mock_commands
    resp = app_info(mock_request, "test_app")
    assert isinstance(resp, HttpResponseRedirect)
    assert resp.status_code == 302, resp
    assert resp.url == "/apps/test_app/logs"


def assert_snapshot(keyword: str, content: str):
    snapshot_file = Path(__file__).parent.joinpath("snapshots", keyword)
    if not snapshot_file.exists():
        with snapshot_file.open("w") as f:
            f.write(content)
    else:
        assert content == snapshot_file.open().read()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key, view_func",
    [
        ("databases", databases),
        ("domains", domains),
        ("config", config),
        ("actions", actions),
        ("logs", logs),
    ],
)
@patch("wharf.tasks.run_ssh_command.delay")
def test_app_infos(
    patched_delay: MagicMock,
    mock_request: HttpRequest,
    key: str,
    view_func: Callable[[HttpRequest, str], HttpResponse],
):
    patched_delay.side_effect = mock_commands
    resp = view_func(mock_request, "test_app")
    assert resp.status_code == 200, resp
    assert isinstance(resp, HttpResponse)
    assert_snapshot(key, resp.text)


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_missing_app_info(patched_delay: MagicMock, mock_request: HttpRequest):
    patched_delay.side_effect = mock_commands
    resp = app_info(mock_request, "missing")
    assert resp.status_code == 404, resp
    content = resp.content.decode("utf-8")
    assert content == "App missing not found"


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_newer_letsencrypt(patched_delay: MagicMock):
    patched_delay.side_effect = custom_mock_commands(
        {
            (
                "plugin:list",
            ): "  letsencrypt          0.22.0 enabled    Automated installation of let's encrypt TLS certificates"
        }
    )
    assert letsencrypt("wharf") is None


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_create_app(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    res = create_app("foo")
    assert res.status_code == 302, res
    assert isinstance(res, HttpResponseRedirect)
    assert res.url.startswith("/apps/foo/wait/"), res


@pytest.mark.django_db
def test_create_duplicate_app():
    models.App.objects.create(name="foo")
    res = create_app("foo")
    assert res.status_code == 400, res
    assert res.content == b"You already have an app called 'foo'", res


def test_login_change(client: Client):
    response = client.get("/", follow=True)
    assert "Initial login is admin/password" in response.text


def test_login_no_change(client: Client, settings: LazySettings):
    settings.ADMIN_PASSWORD = "testpassword"
    response = client.get("/", follow=True)
    assert "Initial login is admin/password" not in response.text


@patch("wharf.tasks.run_ssh_command.delay")
def test_global_config(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    assert global_config() == {"CURL_CONNECT_TIMEOUT": "90", "CURL_TIMEOUT": "600"}


@pytest.mark.django_db
def test_refresh_all(mock_request: HttpRequest, recording_cache: RecordingCache):
    resp = refresh_all(mock_request)
    assert resp.status_code == 302, resp
    assert resp.url == "/", resp
    assert recording_cache.actions == ["clear"]


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_refresh_one(
    patched_delay: MagicMock, mock_request: HttpRequest, recording_cache: RecordingCache
):
    patched_delay.side_effect = mock_commands
    resp = refresh(mock_request, "foo")
    assert resp.status_code == 302, resp
    assert resp.url == "/apps/foo", resp
    assert recording_cache.actions == [
        ("get", ("cmd:plugin:list",)),
        (
            "delete_many",
            (
                [
                    "cmd:config:show foo",
                    "cmd:postgres:info foo",
                    "cmd:redis:info foo",
                    "cmd:ps:report foo",
                    "cmd:domains:report foo",
                    "cmd:letsencrypt:ls",
                ],
            ),
        ),
    ]


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_task_logs_limit(patched_delay: MagicMock, mock_request: HttpRequest):
    patched_delay.side_effect = mock_commands
    test_app = baker.make(models.App, name="test_app")
    baker.make(models.TaskLog, app=test_app, _quantity=20)
    resp = logs(mock_request, "test_app")

    assert isinstance(resp, HttpResponse)
    assert resp.status_code == 200, resp
    log_count = re.findall(r"/logs/[^\"]+", resp.text)
    assert len(log_count) == 10, resp.text


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_create_postgres(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    patched_delay.side_effect = mock_commands
    models.App.objects.get_or_create(name="foo")
    res = create_postgres(mock_request, "foo")
    assert res.status_code == 302, res
    assert res.url.startswith("/apps/foo/wait/"), res

    finished_log(monkeypatch, commands[("postgres:create foo",)])
    check_postgres(mock_request, "foo", "1234")


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_remove_postgres(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    patched_delay.side_effect = mock_commands
    models.App.objects.get_or_create(name="foo")
    res = remove_postgres(mock_request, "foo")
    assert res.status_code == 302, res
    assert res.url.startswith("/apps/foo/wait/"), res

    finished_log(monkeypatch, commands[("postgres:destroy foo --force",)])

    check_remove_postgres(mock_request, "foo", "1234")


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_create_redis(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    patched_delay.side_effect = mock_commands
    models.App.objects.get_or_create(name="foo")
    res = create_redis(mock_request, "foo")
    assert res.status_code == 302, res
    assert res.url.startswith("/apps/foo/wait/"), res

    finished_log(monkeypatch, commands[("redis:create foo",)])
    check_redis(mock_request, "foo", "1234")


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_remove_redis(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    patched_delay.side_effect = mock_commands
    models.App.objects.get_or_create(name="foo")
    res = remove_redis(mock_request, "foo")
    assert res.status_code == 302, res
    assert res.url.startswith("/apps/foo/wait/"), res

    finished_log(monkeypatch, commands[("redis:destroy foo --force",)])

    check_remove_redis(mock_request, "foo", "1234")


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_non_running_app(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    res = process_info("non-running-app")
    assert res == {
        "Deployed": "true",
        "Processes": "1",
        "Ps can scale": "true",
        "Ps computed procfile path": "Procfile",
        "Ps global procfile path": "Procfile",
        "Ps procfile path": "",
        "Ps restart policy": "on-failure:10",
        "Restore": "true",
        "Running": "false",
        "processes": {"web 1": "missing"},
    }


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
@patch("wharf.tasks.get_public_key.delay")
def test_index(
    patched_public_key: MagicMock,
    patched_delay: MagicMock,
    mock_request: HttpRequest,
    monkeypatch: pytest.MonkeyPatch,
):
    patched_delay.side_effect = mock_commands
    patched_public_key.return_value = MockCelery("demo-key")

    def redis_keys(self, key):
        if key == "ssh-check":
            return "ok version"
        raise Exception(key)

    monkeypatch.setattr(
        StrictRedis,
        "get",
        redis_keys,
    )
    resp = index(mock_request)
    assert resp.status_code == 200, resp
    content = resp.content.decode("utf-8")
    assert content.find('<h1 id="list_apps">Wharf</h1>') != -1, content


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
@patch("wharf.tasks.get_public_key.delay")
@patch("wharf.tasks.check_ssh.delay")
def test_index_no_ssh_check(
    patched_check_ssh: MagicMock,
    patched_public_key: MagicMock,
    patched_delay: MagicMock,
    mock_request: HttpRequest,
    monkeypatch: pytest.MonkeyPatch,
):
    patched_delay.side_effect = mock_commands
    patched_check_ssh.return_value = MockCelery(False)
    patched_public_key.return_value = MockCelery("demo-key")

    def redis_keys(self, key):
        if key == "ssh-check":
            return None
        raise Exception(key)

    monkeypatch.setattr(
        StrictRedis,
        "get",
        redis_keys,
    )
    resp = index(mock_request)
    assert resp.status_code == 200, resp
    content = resp.content.decode("utf-8")
    assert (
        content.find('<h1 id="initial-setup-header">Wharf: Initial setup</h1>') != -1
    ), content
    assert content.find('<code id="ssh-key">\n        demo-key\n    </code>') != -1, (
        content
    )


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_setup_letsencrypt(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    models.App.objects.create(name="test_app")
    cast(MagicMock, mock_request).POST = {"email": "foo@bar.com"}
    patched_delay.side_effect = mock_commands
    res = setup_letsencrypt(mock_request, "test_app")
    assert res.status_code == 302, res
    assert isinstance(res, HttpResponseRedirect)
    assert res.url.startswith("/apps/test_app/wait/"), res

    finished_log(
        monkeypatch,
        commands[("letsencrypt:set test_app email foo@bar.com",)]
        + commands[("letsencrypt:enable test_app",)],
    )

    check_res = check_letsencrypt(mock_request, "test_app", "1234")
    assert check_res.status_code == 302, check_res
    assert isinstance(check_res, HttpResponseRedirect)
    assert check_res.url == "/apps/test_app", check_res


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_remove_letsencrypt(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    models.App.objects.create(name="test_app")
    cast(MagicMock, mock_request).POST = {"email": "foo@bar.com"}
    patched_delay.side_effect = mock_commands
    res = remove_letsencrypt(mock_request, "test_app")
    assert res.status_code == 302, res
    assert isinstance(res, HttpResponseRedirect)
    assert res.url.startswith("/apps/test_app/wait/"), res

    finished_log(monkeypatch, commands[("letsencrypt:disable test_app --force",)])

    check_res = check_remove_letsencrypt(mock_request, "test_app", "1234")
    assert check_res.status_code == 302, check_res
    assert isinstance(check_res, HttpResponseRedirect)
    assert check_res.url == "/apps/test_app", check_res


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_app_config_delete(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    models.App.objects.create(name="test_app")
    cast(MagicMock, mock_request).POST = {"key": "FOO_KEY"}
    patched_delay.side_effect = mock_commands
    res = app_config_delete(mock_request, "test_app")
    assert res.status_code == 302, res
    assert isinstance(res, HttpResponseRedirect)
    assert res.url.startswith("/apps/test_app/wait/"), res

    finished_log(monkeypatch, commands[("config:unset test_app FOO_KEY",)])

    check_res = check_app_config_delete(mock_request, "test_app", "1234")
    assert check_res.status_code == 302, check_res
    assert isinstance(check_res, HttpResponseRedirect)
    assert check_res.url == "/apps/test_app", check_res


@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_rename_app(
    patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch
):
    models.App.objects.create(name="test_app")
    cast(MagicMock, mock_request).POST = {"new_name": "bar"}
    patched_delay.side_effect = mock_commands
    res = rename_app(mock_request, "test_app")
    assert res.status_code == 302, res
    assert isinstance(res, HttpResponseRedirect)
    assert res.url.startswith("/apps/test_app/wait/"), res

    finished_log(monkeypatch, commands[("apps:rename test_app bar",)])

    check_res = check_rename_app(mock_request, "test_app", "1234")
    assert check_res.status_code == 302, check_res
    assert isinstance(check_res, HttpResponseRedirect)
    assert check_res.url == "/apps/bar", check_res
