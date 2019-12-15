from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from apps.forms import LoginForm

urlpatterns = [
    path('', include('apps.urls')),
    path('', include('social_django.urls', namespace='social')),
    path('accounts/login/',
         auth_views.LoginView.as_view(template_name="login.html"), name='login'),
    path('admin/', admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
