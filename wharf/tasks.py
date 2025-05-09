from pathlib import Path
from .celery import app
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko import RSAKey
from django.conf import settings
import time
from redis import StrictRedis
import subprocess
import os.path
from git import Repo
from fcntl import fcntl, F_GETFL, F_SETFL
from os import O_NONBLOCK, read
import apps.models as models
from datetime import datetime

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)

def handle_data(key, data):
    data = data.decode("utf-8")
    redis.append(key, data)
    print(data)

def task_key(task_id):
    return "task:%s" % task_id

keyfile = os.path.expanduser("~/.ssh/id_rsa")

def generate_key():
    if not os.path.exists(keyfile):
        keydir = os.path.dirname(keyfile)
        if not os.path.exists(keydir):
            os.mkdir(keydir)
        prv = RSAKey.generate(bits=1024)
        prv.write_private_key_file(keyfile)
        pub = RSAKey(filename=keyfile)
        with open("%s.pub" % keyfile, 'w') as f:
            f.write("%s %s" % (pub.get_name(), pub.get_base64()))
        print("Made new Wharf SSH key")

generate_key()

@app.task
def get_public_key():
    return open("%s.pub" % keyfile).read()

@app.task(bind=True)
def run_ssh_command(self, command: str | list[str]):
    print("Running command", command)
    key = task_key(self.request.id)
    redis.set(key, "")
    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy)
    known_hosts = Path('~/.ssh/known_hosts').expanduser()
    known_hosts_folder = known_hosts.parent
    if not known_hosts_folder.exists():
        known_hosts_folder.mkdir()

    if known_hosts.exists():
        client.load_host_keys(known_hosts.as_posix()) # So that we also save back the new host
    else:
        with known_hosts.open("w") as f:
            f.write("") # so connect doesn't barf when trying to save
        
    if isinstance(command, list):
        commands = command
    else:
        commands = [command]
    for c in commands:
        if os.path.exists(keyfile):
            pkey = RSAKey.from_private_key_file(keyfile)
        else:
            pkey = None
        client.connect(settings.DOKKU_HOST, port=settings.DOKKU_SSH_PORT, username="dokku", pkey=pkey, allow_agent=False, look_for_keys=False)
        transport = client.get_transport()
        assert transport is not None
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
def deploy(self, app_name, git_url):
    models.TaskLog(
        task_id=self.request.id,
        when=datetime.now(),
        app=models.App.objects.get(name=app_name),
        description="Deploying %s" % app_name
    ).save()
    key = task_key(self.request.id)
    app_repo_path = os.path.abspath(os.path.join("repos", app_name))
    if not os.path.exists(app_repo_path):
        redis.append(key, "== Cloning ==\n")
        run_process(key, ["git", "clone", git_url, app_repo_path])
    repo = Repo(app_repo_path)
    try:
        repo.remotes['dokku']
    except IndexError:
        repo.create_remote('dokku', "ssh://dokku@%s:%s/%s" % (settings.DOKKU_HOST, settings.DOKKU_SSH_PORT, app_name))
    redis.append(key, "== Pulling ==\n")
    run_process(key, ["git", "pull"], cwd=app_repo_path)
    redis.append(key, "== Pushing to Dokku ==\n")
    run_process(key, ["git", "push", "-f", "dokku", "master"], cwd=app_repo_path)