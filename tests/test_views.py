from typing import Any, Callable
from unittest.mock import MagicMock, patch
import uuid

from django.conf import LazySettings
from django.http import HttpRequest
from django.test import Client
import pytest
from apps import models
from apps.views import app_info, app_list, check_app, create_app, letsencrypt
from celery.result import AsyncResult
from celery.states import state, SUCCESS
from redis import StrictRedis
from django.core.cache import cache

class MockCelery:
    def __init__(self, res: str):
        self.res = res
        self.id = uuid.uuid4()

    def get(self):
        return self.res
    
commands = {
    ("apps:list", ): """=====> My Apps
wharf""",
("config test_app",): """=====> test_app env vars
DOKKU_APP_RESTORE:  1
DOKKU_APP_TYPE:     dockerfile
DOKKU_PROXY_PORT:   80""",
("config missing", ): " !     App missing does not exist",
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
("logs test_app --num 100",): """2025-04-25T23:07:53.894820268Z app[celery.1]: System check identified some issues:
2025-04-25T23:07:53.895026545Z app[celery.1]:
2025-04-25T23:07:53.895030874Z app[celery.1]: WARNINGS:""",
("domains:report test_app",): """"=====> test_app domains information
       Domains app enabled:           true
       Domains app vhosts:            test_app.vagrant
       Domains global enabled:        true
       Domains global vhosts:         vagrant""",
("postgres:info missing",): " !     Postgres service missing does not exist",
("redis:info missing",): " !     Redis service missing does not exist",
("letsencrypt:ls",): "-----> App name  Certificate Expiry        Time before expiry        Time before renewal",
("letsencrypt:list",): "-----> App name  Certificate Expiry        Time before expiry        Time before renewal",
("ps:report missing",): " !     App missing does not exist",
("logs missing --num 100",): " !     App missing does not exist",
("domains:report missing",): " !     App missing does not exist",
("plugin:list", ): """ letsencrypt          0.9.4 enabled    Automated installation of let's encrypt TLS certificates
  logs                 0.35.18 enabled    dokku core logs plugin
  network              0.35.18 enabled    dokku core network plugin""",
("apps:create foo",): ""
}

def custom_mock_commands(override_commands: dict[Any, str]) -> Callable:
    def _internal(*args):
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
def disable_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cache, "set", lambda _key, _value, _timeout: None)

@patch("wharf.tasks.run_ssh_command.delay")
def test_app_list(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    assert app_list() == ["wharf"]

@patch("wharf.tasks.run_ssh_command.delay")
def test_check_app(patched_delay: MagicMock, mock_request: HttpRequest, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(AsyncResult, "state", state(SUCCESS))
    monkeypatch.setattr(StrictRedis, "get", lambda _self, _key: b"""Creating test_app...
-----> Creating new app virtual host file...""")

    patched_delay.side_effect = mock_commands
    resp = check_app(mock_request, "test_app", "1234")
    assert resp.status_code == 302, resp
    assert resp.url == "/apps/test_app"

@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_app_info(patched_delay: MagicMock, mock_request: HttpRequest):
    patched_delay.side_effect = mock_commands
    resp = app_info(mock_request, "test_app")    
    assert resp.status_code == 200, resp
    content = resp.content.decode('utf-8')

    expected_contents = ["""<h1 id="app_page" >Wharf: test_app</h1>\n<a href="/">Return to apps index</a><br />\n\n<h3>Actions</h3>\n\nCan\'t deploy due to missing GITHUB_URL in config (which should be set to the "Clone with HTTPS" url from Github)\n\n<h2>Task logs</h2>\n\nNo tasks run yet\n\n<h2>Domains</h2>\n\n<ul>\n  \n    <li>\n      <a href="http://test_app.vagrant">test_app.vagrant</a>\n      <form class="d-inline" action="/apps/test_app/remove_domain" method="POST">""",
"""<input type="hidden" name="name" value="test_app.vagrant" />\n        <button type="submit" class="btn btn-primary">Delete \'test_app.vagrant\' domain</button>\n      </form>\n    </li>\n  \n</ul>\n\n<h3>New domain</h3>\n<form action="/apps/test_app/add_domain" method="POST">""",
"""<div class="form-group">\n  \n    \n    <label class="control-label  required" for="id_name">Domain name</label>\n  \n\n  <div class="">\n    <input type="text" name="name" maxlength="100" class=" form-control" required id="id_name">\n    \n    \n  </div>\n  \n</div>\n\n  <input class="form-control" type="submit" value="Submit" />\n</form>\n<h2>Config</h2>\n<ul class=config>\n  \n    <li>DOKKU_APP_RESTORE = 1</li>\n  \n    <li>DOKKU_APP_TYPE = dockerfile</li>\n  \n    <li>DOKKU_PROXY_PORT = 80</li>\n  \n</ul>\n<h3>New item</h3>\n<form action="/apps/test_app" method="POST">""",
  """<div class="form-group">\n  \n    \n    <label class="control-label  required" for="id_key">key</label>\n  \n\n  <div class="">\n    <input type="text" name="key" maxlength="100" class=" form-control" required id="id_key">\n    \n    \n  </div>\n  \n</div>\n\n  <div class="form-group">\n  \n    \n    <label class="control-label  required" for="id_value">value</label>\n  \n\n  <div class="">\n    <input type="text" name="value" maxlength="300" class=" form-control" required id="id_value">\n    \n    \n  </div>\n  \n</div>\n\n  <input class="form-control" type="submit" value="Submit" id="config_add" />\n</form>\n<h3>Postgres</h3>\n\nStatus: \n\n<h3>Redis</h3>\n\nStatus: \n\n<h3>Let\'s Encrypt</h3>\n\n<form class="form-inline" action="/apps/test_app/setup_letsencrypt" method="POST">""",
"""<button type="submit" class="btn btn-primary">Setup Let\'s Encrypt</button>\n</form>\n\n<h3>Process Info</h3>\n<ul>\n  \n  <li>Deployed: true</li>\n  \n  <li>Processes: 2</li>\n  \n  <li>Ps can scale: true</li>\n  \n  <li>Ps computed procfile path: Procfile</li>\n  \n  <li>Ps global procfile path: Procfile</li>\n  \n  <li>Ps procfile path: </li>\n  \n  <li>Ps restart policy: on-failure:10</li>\n  \n  <li>Restore: true</li>\n  \n  <li>Running: true</li>\n  \n</ul>\n<h3>Processes</h3>\n<ul>\n  \n  <li>celery 1: running</li>\n  \n  <li>web 1: running</li>\n  \n</ul>\n<h3>Logs</h3>\n<pre>\n2025-04-25T23:07:53.894820268Z app[celery.1]: System check identified some issues:\n2025-04-25T23:07:53.895026545Z app[celery.1]:\n2025-04-25T23:07:53.895030874Z app[celery.1]: WARNINGS:\n</pre>"""]
    for expected_content in expected_contents:        
        assert expected_content in content    

@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_missing_app_info(patched_delay: MagicMock, mock_request: HttpRequest):
    patched_delay.side_effect = mock_commands
    resp = app_info(mock_request, "missing")
    assert resp.status_code == 200, resp
    content = resp.content.decode('utf-8')
    expected_contents = ["""<h1 id="app_page" >Wharf: missing</h1>\n<a href="/">Return to apps index</a><br />\n\n<h3>Actions</h3>\n\nCan\'t deploy due to missing GITHUB_URL in config (which should be set to the "Clone with HTTPS" url from Github)\n\n<h2>Task logs</h2>\n\nNo tasks run yet\n\n<h2>Domains</h2>\n\n<ul>\n  \n</ul>\n\n<h3>New domain</h3>\n<form action="/apps/missing/add_domain" method="POST">""", """<div class="form-group">\n  \n    \n    <label class="control-label  required" for="id_name">Domain name</label>\n  \n\n  <div class="">\n    <input type="text" name="name" maxlength="100" class=" form-control" required id="id_name">\n    \n    \n  </div>\n  \n</div>\n\n  <input class="form-control" type="submit" value="Submit" />\n</form>\n<h2>Config</h2>\n<ul class=config>\n  \n</ul>\n<h3>New item</h3>\n<form action="/apps/missing" method="POST">""",
    """<label class="control-label  required" for="id_key">key</label>\n  \n\n  <div class="">\n    <input type="text" name="key" maxlength="100" class=" form-control" required id="id_key">\n    \n    \n  </div>\n  \n</div>\n\n  <div class="form-group">\n  \n    \n    <label class="control-label  required" for="id_value">value</label>\n  \n\n  <div class="">\n    <input type="text" name="value" maxlength="300" class=" form-control" required id="id_value">\n    \n    \n  </div>\n  \n</div>\n\n  <input class="form-control" type="submit" value="Submit" id="config_add" />\n</form>\n<h3>Postgres</h3>\n\n<form class="form-inline" action="/apps/missing/create_postgres" method="POST">""",
    """<h3>Redis</h3>\n\n<form class="form-inline" action="/apps/missing/create_redis" method="POST">""", """<button type="submit" class="btn btn-primary">Create redis db</button>\n</form>\n\n<h3>Let\'s Encrypt</h3>\n\n<form class="form-inline" action="/apps/missing/setup_letsencrypt" method="POST">""",
    """<button type="submit" class="btn btn-primary">Setup Let\'s Encrypt</button>\n</form>\n\n<h3>Process Info</h3>\n<ul>\n  \n</ul>\n<h3>Processes</h3>\n<ul>\n  \n</ul>\n<h3>Logs</h3>\n<pre>\n!     App missing does not exist\n</pre>"""]
    for expected_content in expected_contents:
        assert expected_content in content

@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_newer_letsencrypt(patched_delay: MagicMock):
    patched_delay.side_effect = custom_mock_commands({("plugin:list", ): "  letsencrypt          0.22.0 enabled    Automated installation of let's encrypt TLS certificates"
})
    assert letsencrypt("wharf") == None

@pytest.mark.django_db
@patch("wharf.tasks.run_ssh_command.delay")
def test_create_app(patched_delay: MagicMock):
    patched_delay.side_effect = mock_commands
    res = create_app("foo")
    assert res.status_code == 302, res
    assert res.url.startswith("/apps/foo/wait/"), res

@pytest.mark.django_db
def test_create_duplicate_app():
    models.App.objects.create(name="foo")
    res = create_app("foo")
    assert res.status_code == 400, res
    assert res.content == b"You already have an app called 'foo'", res

def test_login_change(client: Client):
    response = client.get('/', follow=True)
    assert "Initial login is admin/password" in response.text

def test_login_no_change(client: Client, settings: LazySettings):
    settings.ADMIN_PASSWORD = "testpassword"
    response = client.get('/', follow=True)
    assert "Initial login is admin/password" not in response.text