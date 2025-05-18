from typing import Any
from django.conf import settings

def helpers(request: Any):
    return {"HAS_LOGIN_SET": settings.ADMIN_LOGIN != "admin" or settings.ADMIN_PASSWORD != "password"}