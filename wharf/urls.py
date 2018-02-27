from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', include('apps.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(template_name="login.html"), name='login'),
    path('admin/', admin.site.urls),
]
