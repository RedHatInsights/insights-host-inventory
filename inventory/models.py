import uuid
from django.db import models
from django.contrib.postgres.fields import JSONField


class Entity(models.Model):
    account_number = models.CharField(max_length=10)
    display_name = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["account_number"])]

    def __str__(self):
        return self.display_name


class Fact(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="facts")
    namespace = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=200)

    class Meta:
        indexes = [models.Index(fields=["namespace"]), models.Index(fields=["name"])]


class Tag(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=200)

    class Meta:
        indexes = [models.Index(fields=["name"])]


class AlternativeId(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="ids")
    namespace = models.CharField(max_length=200)
    value = models.CharField(max_length=200)

    class Meta:
        indexes = [models.Index(fields=["namespace"]), models.Index(fields=["value"])]
