from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('apps/<app_name>', views.app_info, name='app_info'),
]