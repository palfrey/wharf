from .celery import app
from paramiko.client import SSHClient
from django.conf import settings
import select
import time
from redis import StrictRedis
import subprocess
import os.path
from git import Repo

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)

def handle_data(key, data):
    data = data.decode("utf-8")
    redis.append(key, data)
    print(data)

def task_key(task_id):
    return "task:%s" % task_id

@app.task(bind=True)
def run_ssh_command(self, command):
    key = task_key(self.request.id)
    client = SSHClient()
    client.load_system_host_keys()
    client.connect(settings.DOKKU_HOST, port=settings.DOKKU_SSH_PORT, username="dokku")
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(command)
    while True:
        anything = False
        while channel.recv_ready():
            data = channel.recv(1024)
            handle_data(key, data)
            anything = True
        while channel.recv_stderr_ready():
            data = channel.recv_stderr(1024)
            handle_data(key, data)
            anything = True
        if not anything:
            if channel.exit_status_ready():
                return redis.get(key).decode("utf-8")
            time.sleep(0.1)

def run_process(key, cmd, cwd=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd)
    while True:
        line = p.stdout.read()
        if line == b'' and p.poll() != None:
            break
        handle_data(key, line)
    if p.poll()!=0:
        raise Exception

@app.task(bind=True)
def deploy(self, app, git_url):
    key = task_key(self.request.id)
    app_repo_path = os.path.abspath(os.path.join("repos", app))
    if not os.path.exists(app_repo_path):
        run_process(key, ["git", "clone", git_url, app_repo_path])
    repo = Repo(app_repo_path)
    try:
        repo.remotes['dokku']
    except IndexError:
        repo.create_remote('dokku', "ssh://dokku@%s:%s/%s" % (settings.DOKKU_HOST, settings.DOKKU_SSH_PORT, app))
    run_process(key, ["git", "pull"], cwd=app_repo_path)
    run_process(key, ["git", "push", "dokku", "master"], cwd=app_repo_path)