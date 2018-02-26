from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('refresh', views.refresh_all, name='refresh_all'),
    path('create_app', views.create_app, name='create_app'),
    path('global_config_set', views.global_config_set, name='global_config_set'),
    path('global_config_check/<task_id>', views.check_global_config_set, name='check_global_config_set'),
    path('apps/<app_name>/check_app/<task_id>', views.check_app, name='check_app'),
    path('apps/<app_name>', views.app_info, name='app_info'),
    path('apps/<app_name>/wait/<task_id>/<after>', views.wait_for_command, name='wait_for_command'),
    path('apps/<app_name>/check_app_config_set/<task_id>', views.check_app_config_set, name='check_app_config_set'),
    path('apps/<app_name>/deploy', views.deploy, name='deploy'),
    path('apps/<app_name>/check_deploy/<task_id>', views.check_deploy, name='check_deploy'),
    path('apps/<app_name>/create_postgres', views.create_postgres, name='create_postgres'),
    path('apps/<app_name>/check_postgres/<task_id>', views.check_postgres, name='check_postgres'),
    path('apps/<app_name>/create_redis', views.create_redis, name='create_redis'),
    path('apps/<app_name>/check_redis/<task_id>', views.check_redis, name='check_redis'),
    path('apps/<app_name>/setup_letsencrypt', views.setup_letsencrypt, name='setup_letsencrypt'),
    path('apps/<app_name>/check_letsencrypt/<task_id>', views.check_letsencrypt, name='check_letsencrypt'),
    path('apps/<app_name>/add_domain', views.add_domain, name='add_domain'),
    path('apps/<app_name>/check_domain/<task_id>', views.check_domain, name='check_domain'),
    path('logs/<task_id>', views.show_log, name='show_log'),
]