from .models import Entity, Fact, Tag, AlternativeId
from rest_framework import serializers


class EntitySerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = Entity
        fields = ("id", "account_number", "display_name", "ids", "tags", "facts")


class FactSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Fact
        fields = ("namespace", "name", "value")


class TagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = ("name", "value")


class AlternativeIdSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = AlternativeId
        fields = ("namespace", "value")
