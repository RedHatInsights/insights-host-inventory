from .models import Entity, Tag
from dynamic_rest import serializers
from dynamic_rest.fields.fields import DynamicRelationField


class EntitySerializer(serializers.DynamicModelSerializer):

    tags = DynamicRelationField('TagSerializer', many=True)

    class Meta:
        model = Entity
        fields = "__all__"


class TagSerializer(serializers.DynamicModelSerializer):

    class Meta:
        model = Tag
        fields = "__all__"
