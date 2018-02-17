from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('apps/<app_name>', views.app_info, name='app_info'),
    path('apps/<app_name>/wait/<task_id>/<after>', views.wait_for_command, name='wait_for_command'),
    path('apps/<app_name>/check_app_config_set/<task_id>', views.check_app_config_set, name='check_app_config_set')
]