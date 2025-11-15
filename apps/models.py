import datetime
import uuid

import humanize
from django.db import models


class App(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=256, unique=True)
    github_url = models.URLField()


class TaskLog(models.Model):
    task_id = models.CharField(max_length=256, primary_key=True)
    when = models.DateTimeField()
    success = models.BooleanField(null=True, blank=True)
    app = models.ForeignKey(App, on_delete=models.CASCADE)
    description = models.CharField(max_length=256)

    def nice_when(self):
        return humanize.naturaltime(
            datetime.datetime.now(datetime.timezone.utc) - self.when
        )
