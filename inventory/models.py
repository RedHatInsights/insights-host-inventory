import uuid
from django.db import models
from django.contrib.postgres.fields import JSONField


class Entity(models.Model):
    account_number = models.CharField(max_length=10)
    facts = JSONField(null=True)
    display_name = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    tags = JSONField(null=True)
    ids = JSONField(null=True)

    class Meta:
        indexes = [models.Index(fields=["account_number"])]

    def __str__(self):
        return self.display_name
