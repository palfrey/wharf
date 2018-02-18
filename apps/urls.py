from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('apps/<app_name>', views.app_info, name='app_info'),
    path('apps/<app_name>/wait/<task_id>/<after>', views.wait_for_command, name='wait_for_command'),
    path('apps/<app_name>/check_app_config_set/<task_id>', views.check_app_config_set, name='check_app_config_set'),
    path('apps/<app_name>/deploy', views.deploy, name='deploy'),
    path('apps/<app_name>/check_deploy/<task_id>', views.check_deploy, name='check_deploy'),
]