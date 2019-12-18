from django.urls import path, include
from django.contrib.staticfiles.storage import staticfiles_storage
from django.views.generic.base import RedirectView
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('status', views.utils.status, name='status'),
    path('refresh', views.utils.refresh_all, name='refresh_all'),
    path('create_app', views.apps.create_app, name='create_app'),
    path('global_config_bulk_set', views.configuration.global_config_bulk_set, name='global_config_bulk_set'),
    path('apps/<app_name>/check_global_config_set/<task_id>', views.configuration.check_global_config_set, name='check_global_config_set'),

    path('apps/<app_name>/check_app/<task_id>', views.apps.check_app, name='check_app'),
    path('apps/<app_name>', views.app_info, name='app_info'),
    path('apps/<app_name>/wait/<task_id>/<after>', views.wait_for_command, name='wait_for_command'),
    path('apps/<app_name>/check_app_config_set/<task_id>', views.configuration.check_app_config_set, name='check_app_config_set'),
    path('apps/<app_name>/deploy', views.apps.deploy, name='deploy'),
    path('apps/<app_name>/check_deploy/<task_id>', views.apps.check_deploy, name='check_deploy'),
    path('apps/<app_name>/check_rebuild/<task_id>', views.apps.check_rebuild, name='check_rebuild'),

    path('apps/<app_name>/create_postgres', views.postgres.create_postgres, name='create_postgres'),
    path('apps/<app_name>/check_postgres/<task_id>', views.postgres.check_postgres, name='check_postgres'),
    path('apps/<app_name>/check_postgres_removal/<task_id>', views.postgres.check_postgres_removal, name='check_postgres_removal'),
    path('apps/<app_name>/<link_name>/remove_postgres', views.postgres.remove_postgres, name='remove_postgres'),

    path('apps/<app_name>/create_redis', views.redis.create_redis, name='create_redis'),
    path('apps/<app_name>/check_redis/<task_id>', views.redis.check_redis, name='check_redis'),
    path('apps/<app_name>/check_redis_removal/<task_id>', views.redis.check_redis_removal, name='check_redis_removal'),
    path('apps/<app_name>/<link_name>/remove_redis', views.redis.remove_redis, name='remove_redis'),

    path('apps/<app_name>/create_mariadb', views.mariadb.create_mariadb, name='create_mariadb'),
    path('apps/<app_name>/check_mariadb/<task_id>', views.mariadb.check_mariadb, name='check_mariadb'),
    path('apps/<app_name>/check_mariadb_removal/<task_id>', views.mariadb.check_mariadb_removal, name='check_mariadb_removal'),
    path('apps/<app_name>/<link_name>/remove_mariadb', views.mariadb.remove_mariadb, name='remove_mariadb'),

    path('apps/<app_name>/add_buildpack', views.buildpacks.add_buildpack, name='add_buildpack'),
    path('apps/<app_name>/check_buildpack/<task_id>', views.buildpacks.check_buildpack, name='check_buildpack'),
    path('apps/<app_name>/remove_buildpack', views.buildpacks.remove_buildpack, name='remove_buildpack'),
    path('apps/<app_name>/check_buildpack_removal/<task_id>', views.buildpacks.check_buildpack_removal, name='check_buildpack_removal'),

    path('apps/<app_name>/setup_letsencrypt', views.letsencrypt.setup_letsencrypt, name='setup_letsencrypt'),
    path('apps/<app_name>/check_letsencrypt/<task_id>', views.check_letsencrypt, name='check_letsencrypt'),

    path('apps/<app_name>/add_domain', views.domains.add_domain, name='add_domain'),
    path('apps/<app_name>/check_domain/<task_id>', views.domains.check_domain, name='check_domain'),
    path('apps/<app_name>/remove_domain', views.domains.remove_domain, name='remove_domain'),

    path('logs/<task_id>', views.show_log, name='show_log'),
    path('webhook', views.apps.github_webhook),
    path('favicon.ico', RedirectView.as_view(url=staticfiles_storage.url('favicon.ico'),permanent=False), name="favicon"),
]
