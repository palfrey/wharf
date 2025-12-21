from typing import List, cast
from unittest.mock import MagicMock, _Call

from django.contrib.messages.storage.base import Message
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponseRedirect
from django.test import RequestFactory

import wharf.auth


class RequestWithMessages(WSGIRequest):
    _messages: MagicMock


def test_login_required_middleware_no_auth(rf: RequestFactory) -> None:
    mw = wharf.auth.LoginRequiredMiddleware(None)
    request = rf.get("/test")
    request.user = MagicMock()
    request.user.is_authenticated = False
    res = mw(request)
    assert isinstance(res, HttpResponseRedirect)
    assert res.url == "/accounts/login/?next=/test"


def authed_request_with_messages(
    rf: RequestFactory, messages: List[Message]
) -> tuple[RequestWithMessages, MagicMock]:
    request = cast(RequestWithMessages, rf.get("/test"))
    request.user = MagicMock()
    request.user.is_authenticated = True
    mock_messages = MagicMock()
    request._messages = MagicMock(
        add=mock_messages, __iter__=lambda _self: iter(messages)
    )
    return (request, mock_messages)


def test_login_required_middleware_authed(rf: RequestFactory) -> None:
    mw = wharf.auth.LoginRequiredMiddleware(lambda r: None)
    (request, mock_messages) = authed_request_with_messages(rf, [])
    mw(request)
    mock_messages.assert_called_once()
    call = cast(_Call, mock_messages.call_args)
    assert len(call.args) == 3, call
    assert call.args[0] == 30, call
    assert call.args[1].startswith(
        "ADMIN_PASSWORD is in plain text. Set it to pbkdf2_sha256$1200000$"
    ), call
    assert call.args[2] == "", call


def test_login_required_middleware_existing_message(rf: RequestFactory) -> None:
    mw = wharf.auth.LoginRequiredMiddleware(lambda r: None)
    (request, mock_messages) = authed_request_with_messages(
        rf,
        [
            Message(
                30,
                "ADMIN_PASSWORD is in plain text. Set it to pbkdf2_sha256$1200000$",
                "",
            )
        ],
    )
    mw(request)
    mock_messages.assert_not_called()
