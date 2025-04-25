# From http://avilpage.com/2017/05/how-to-auto-reload-celery-workers-in-development.html
import shlex
import subprocess

from django.core.management.base import BaseCommand
from django.utils import autoreload


def restart_celery():
    cmd = 'pkill -9 celery'
    subprocess.call(shlex.split(cmd))
    cmd = 'celery -A wharf worker -l info -B'
    subprocess.call(shlex.split(cmd))

class Command(BaseCommand):
    def handle(self, *args, **options):
        print('Starting celery worker with autoreload...')
        autoreload.run_with_reloader(restart_celery)