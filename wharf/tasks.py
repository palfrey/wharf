import os.path
import signal
import subprocess
import time
from datetime import datetime
from fcntl import F_GETFL, F_SETFL, fcntl
from os import O_NONBLOCK, read
from pathlib import Path
from typing import cast

from celery import Task
from django.conf import settings
from git import Repo
from paramiko import RSAKey
from paramiko.client import AutoAddPolicy, SSHClient
from redis import StrictRedis

import apps.models as models

from .celery import app

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)


def handle_data(key, raw_data: bytes):
    data = raw_data.decode("utf-8", "replace")
    redis.append(key, data)
    print(data)


def task_key(task_id: object) -> str:
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
        with open("%s.pub" % keyfile, "w") as f:
            f.write("%s %s" % (pub.get_name(), pub.get_base64()))
        print("Made new Wharf SSH key")


generate_key()


@app.task
def get_public_key():
    return open("%s.pub" % keyfile).read()


daemon_socket = "/var/run/dokku-daemon/dokku-daemon.sock"


def command_exists(name: str) -> bool:
    for segment in os.environ.get("PATH", "").split(":"):
        if Path(segment).joinpath(name).exists():
            return True
    return False


def has_daemon():
    return (
        os.path.exists(daemon_socket)
        and os.access(daemon_socket, os.W_OK)
        and command_exists("nc")
    )


# From https://github.com/dokku/dokku-daemon?tab=readme-ov-file#usage-within-a-dokku-app
def run_with_daemon(key: str, command: str, timeout=60) -> bool:
    subprocess_command = [
        "nc",
        "-q",
        "2",  # time to wait after eof
        "-w",
        "2",  # timeout
        "-U",
        daemon_socket,  # socket to talk to
    ]

    ps = subprocess.Popen(["echo", command], stdout=subprocess.PIPE)

    with subprocess.Popen(
        subprocess_command,
        stdin=ps.stdout,
        stdout=subprocess.PIPE,
        preexec_fn=os.setsid,
    ) as process:
        try:
            output = process.communicate(timeout=timeout)[0]
            handle_data(key, output)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGINT)  # send signal to the process group
            output = process.communicate()[0]
            handle_data(key, output)
    ps.wait(timeout)

    return ps.returncode == 0


@app.task(bind=True)
def run_ssh_command(self: Task, command: str | list[str]):
    print("Running command", command)
    key = task_key(self.request.id)
    redis.set(key, "")
    if not has_daemon():
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy)
        known_hosts = Path("~/.ssh/known_hosts").expanduser()
        known_hosts_folder = known_hosts.parent
        if not known_hosts_folder.exists():
            known_hosts_folder.mkdir()

        if known_hosts.exists():
            client.load_host_keys(
                known_hosts.as_posix()
            )  # So that we also save back the new host
        else:
            with known_hosts.open("w") as f:
                f.write("")  # so connect doesn't barf when trying to save
    else:
        client = None

    if isinstance(command, list):
        commands = command
    else:
        commands = [command]
    for c in commands:
        if client is None:
            run_with_daemon(key, c)
        else:
            if os.path.exists(keyfile):
                pkey = RSAKey.from_private_key_file(keyfile)
            else:
                pkey = None
            client.connect(
                settings.DOKKU_HOST,
                port=settings.DOKKU_SSH_PORT,
                username="dokku",
                pkey=pkey,
                allow_agent=False,
                look_for_keys=False,
            )
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
    return cast(bytes, redis.get(key)).decode("utf-8")


def set_nb(pipe):
    flags = fcntl(pipe, F_GETFL)
    fcntl(pipe, F_SETFL, flags | O_NONBLOCK)


def run_process(key, cmd, cwd=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    set_nb(p.stdout)
    set_nb(p.stderr)
    while True:
        try:
            assert p.stdout is not None
            out = read(p.stdout.fileno(), 1024)
        except BlockingIOError:
            out = b""
        try:
            assert p.stderr is not None
            err = read(p.stderr.fileno(), 1024)
        except BlockingIOError:
            err = b""
        handle_data(key, out)
        handle_data(key, err)
        if out == b"" and err == b"":
            if p.poll() is not None:
                break
            time.sleep(0.1)
    if p.poll() != 0:
        raise Exception


@app.task(bind=True)
def deploy(self: Task, app_name: str, git_url: str, git_branch: str):
    models.TaskLog(
        task_id=self.request.id,
        when=datetime.now(),
        app=models.App.objects.get(name=app_name),
        description="Deploying %s" % app_name,
    ).save()
    key = task_key(self.request.id)
    app_repo_path = os.path.abspath(os.path.join("repos", app_name))
    if not os.path.exists(app_repo_path):
        redis.append(key, "== Cloning ==\n")
        run_process(key, ["git", "clone", git_url, app_repo_path])
    repo = Repo(app_repo_path)
    try:
        repo.remotes["dokku"]
    except IndexError:
        repo.create_remote(
            "dokku",
            "ssh://dokku@%s:%s/%s"
            % (settings.DOKKU_HOST, settings.DOKKU_SSH_PORT, app_name),
        )
    redis.append(key, "== Pulling ==\n")
    run_process(key, ["git", "pull"], cwd=app_repo_path)
    redis.append(key, "== Pushing to Dokku ==\n")
    run_process(key, ["git", "push", "-f", "dokku", git_branch], cwd=app_repo_path)
