import django

import types
import unittest
import wharf.auth

django.setup()


class AuthTests(unittest.TestCase):
    def test_login_required_middleware(self):
        mw = wharf.auth.LoginRequiredMiddleware(None)
        request = types.SimpleNamespace()
        request.path_info = "foo"
        request.get_host = lambda: None
        request.user = types.SimpleNamespace()
        request.user.is_authenticated = False
        mw(request)
