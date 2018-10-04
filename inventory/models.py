from django.db import models
from django.contrib.postgres.fields import JSONField


class Host(models.Model):
    account = models.CharField(max_length=10)
    display_name = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    facts = JSONField(null=True)
    tags = JSONField(null=True)
    canonical_facts = JSONField(null=True)

    class Meta:
        indexes = [models.Index(fields=["account"])]
        ordering = ["id"]

    def __str__(self):
        tmpl = "[Host '%s' canonical_facts=%s]"
        return tmpl % (self.display_name, self.canonical_facts)
