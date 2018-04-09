from .models import Entity, EntityRelationship
from rest_framework import serializers


class EntitySerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = Entity
        fields = ("id", "account_number", "display_name", "tags", "facts")
