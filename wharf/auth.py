from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.contrib import messages
from re import compile
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

class SettingsBackend:
    """
    Authenticate against the settings ADMIN_LOGIN and ADMIN_PASSWORD.

    Use the login name and a hash of the password. For example:

    ADMIN_LOGIN = 'admin'
    ADMIN_PASSWORD = 'pbkdf2_sha256$30000$Vo0VlMnkR4Bk$qEvtdyZRWTcOsCnI/oQ7fVOu1XAURIZYoOZ3iq8Dr4M='

    If ADMIN_PASSWORD is unhashed, then this returns a message warning you about that
    """

    def authenticate(self, request, username=None, password=None):
        login_valid = (settings.ADMIN_LOGIN == username)
        if settings.ADMIN_PASSWORD.startswith("pbkdf2_sha256"):
            pwd_valid = check_password(password, settings.ADMIN_PASSWORD)
        else:
            pwd_valid = password == settings.ADMIN_PASSWORD
        if login_valid and pwd_valid:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                # Create a new user. There's no need to set a password
                # because only the password from settings.py is checked.
                user = User(username=username)
                user.is_staff = True
                user.is_superuser = True
                user.save()
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

# Based on https://gist.github.com/agusmakmun/b71ac536124e0535a8b076989f8cfcd3
EXEMPT_URLS = [compile(settings.LOGIN_URL.lstrip('/'))]
if hasattr(settings, 'LOGIN_EXEMPT_URLS'):
    EXEMPT_URLS += [compile(expr) for expr in settings.LOGIN_EXEMPT_URLS]

class LoginRequiredMiddleware:
    """
    Middleware that requires a user to be authenticated to view any page other
    than LOGIN_URL. Exemptions to this requirement can optionally be specified
    in settings via a list of regular expressions in LOGIN_EXEMPT_URLS (which
    you can copy from your urls.py).
    Requires authentication middleware and template context processors to be
    loaded. You'll get an error if they aren't.

    Based on https://djangosnippets.org/snippets/1179/
    My modification adds 'next' GET parameter to enable redirection after
    successful login.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path_info.lstrip('/')
            if not any(m.match(path) for m in EXEMPT_URLS):
                redirect_to = settings.LOGIN_URL
                # Add 'next' GET variable to support redirection after login
                if len(path) > 0 and url_has_allowed_host_and_scheme(url=request.path_info, allowed_hosts=None):
                    redirect_to = "%s?next=%s" %(settings.LOGIN_URL, request.path_info)
                return HttpResponseRedirect(redirect_to)
        elif not settings.ADMIN_PASSWORD.startswith("pbkdf2_sha256"):
            better_password = make_password(settings.ADMIN_PASSWORD)
            messages.warning(request, "ADMIN_PASSWORD is in plain text. Set it to %s instead" % better_password)
        return self.get_response(request)