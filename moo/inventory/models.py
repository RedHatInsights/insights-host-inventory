import uuid
from django.db import models
from django.contrib.postgres.fields import JSONField


class Tag(models.Model):
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=200, null=True)

    def __str__(self):
        return "{}={}".format(self.name, self.value)


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    facts = JSONField(null=True)
    display_name = models.CharField(max_length=200)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag)
    relationships = models.ManyToManyField(
        "self",
        through="EntityRelationship",
        through_fields=("from_entity", "to_entity"),
        symmetrical=False,
    )

    def __str__(self):
        return self.display_name


class EntityRelationship(models.Model):

    from_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="to_entity"
    )
    to_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="from_entity"
    )
    kind = models.CharField(max_length=200)

    def __str__(self):
        return "({}) -[{}]-> ({})".format(self.from_entity, self.kind, self.to_entity)
