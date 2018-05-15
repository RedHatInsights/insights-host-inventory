from .models import Entity, Fact, Tag, AlternativeId
from rest_framework import serializers


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


class EntitySerializer(serializers.HyperlinkedModelSerializer):

    facts = FactSerializer(many=True)
    tags = TagSerializer(many=True)
    ids = AlternativeIdSerializer(many=True)

    class Meta:
        model = Entity
        fields = "__all__"
