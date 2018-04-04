import uuid
from django.db import models
from django.contrib.postgres.fields import JSONField


class Tag(models.Model):
    name = models.CharField(max_length=200)


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    facts = JSONField()
    display_name = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        return self.display_name
