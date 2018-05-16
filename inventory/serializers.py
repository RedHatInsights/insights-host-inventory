from .models import Entity
from rest_framework import serializers


class EntitySerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = Entity
        fields = "__all__"
