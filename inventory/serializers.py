from dynamic_rest.serializers import DynamicModelSerializer
from dynamic_rest.fields import DynamicRelationField
from inventory.models import Entity, Tag


class TagSerializer(DynamicModelSerializer):
    class Meta:
        model = Tag
        name = "tag"
        fields = ("id", "namespace", "name", "value")


class EntitySerializer(DynamicModelSerializer):
    class Meta:
        model = Entity
        name = "entity"
        fields = ("canonical_facts", "facts", "tags", "display_name", "account")

    tags = DynamicRelationField("TagSerializer", many=True)
