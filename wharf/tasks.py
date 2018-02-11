from .celery import app
from paramiko.client import SSHClient
from django.conf import settings
import select
import time
from redis import StrictRedis

redis = StrictRedis.from_url(settings.CELERY_BROKER_URL)

def handle_data(key, data):
    data = data.decode("utf-8")
    redis.append(key, data)
    print(data)

@app.task(bind=True)
def run_command(self, command):
    key = "task:%s" % self.request.id
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