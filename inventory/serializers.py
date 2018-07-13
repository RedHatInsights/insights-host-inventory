from dynamic_rest.serializers import DynamicModelSerializer
from dynamic_rest.fields import DynamicRelationField
from inventory.models import Entity, Tag


class TagSerializer(DynamicModelSerializer):
    class Meta:
        model = Tag
        name = "tag"
        fields = ("namespace", "name", "value")


class EntitySerializer(DynamicModelSerializer):
    class Meta:
        model = Entity
        name = "entity"
        fields = ("ids", "facts", "tags", "display_name")

    tags = DynamicRelationField("TagSerializer", many=True)
