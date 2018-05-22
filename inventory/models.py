from django.db import models
from django.contrib.postgres.fields import JSONField


class Tag(models.Model):
    namespace = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "%s=%s" % (self.name, self.value)


class Entity(models.Model):
    account_number = models.CharField(max_length=10)
    display_name = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    facts = JSONField(null=True)
    tags = models.ManyToManyField(Tag)
    ids = JSONField(null=True)

    class Meta:
        indexes = [models.Index(fields=["account_number"])]

    def __str__(self):
        return self.display_name
