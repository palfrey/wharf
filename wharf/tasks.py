from .celery import app
from paramiko.client import SSHClient
from django.conf import settings
import select
import time
from redis import StrictRedis
import subprocess
import os.path
from git import Repo
from fcntl import fcntl, F_GETFL, F_SETFL
from os import O_NONBLOCK, read

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
    if type(command) == list:
        commands = command
    else:
        commands = [command]
    for c in commands:
        client.connect(settings.DOKKU_HOST, port=settings.DOKKU_SSH_PORT, username="dokku")
        transport = client.get_transport()
        channel = transport.open_session()
        channel.exec_command(c)
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
                    break
                time.sleep(0.1)
    return redis.get(key).decode("utf-8")

def set_nb(pipe):
    flags = fcntl(pipe, F_GETFL)
    fcntl(pipe, F_SETFL, flags | O_NONBLOCK)

def run_process(key, cmd, cwd=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    set_nb(p.stdout)
    set_nb(p.stderr)
    while True:
        try:
            out = read(p.stdout.fileno(), 1024)
        except BlockingIOError:
            out = b""
        try:
            err = read(p.stderr.fileno(), 1024)
        except BlockingIOError:
            err = b""
        handle_data(key, out)
        handle_data(key, err)
        if out == b'' and err == b'':
            if p.poll() != None:
                break
            time.sleep(0.1)
    if p.poll()!=0:
        raise Exception

@app.task(bind=True)
def deploy(self, app, git_url):
    key = task_key(self.request.id)
    app_repo_path = os.path.abspath(os.path.join("repos", app))
    if not os.path.exists(app_repo_path):
        redis.append(key, "== Cloning ==\n")
        run_process(key, ["git", "clone", git_url, app_repo_path])
    repo = Repo(app_repo_path)
    try:
        repo.remotes['dokku']
    except IndexError:
        repo.create_remote('dokku', "ssh://dokku@%s:%s/%s" % (settings.DOKKU_HOST, settings.DOKKU_SSH_PORT, app))
    redis.append(key, "== Pulling ==\n")
    run_process(key, ["git", "pull"], cwd=app_repo_path)
    redis.append(key, "== Pushing to Dokku ==\n")
    run_process(key, ["git", "push", "dokku", "master"], cwd=app_repo_path)