from dynamic_rest.serializers import DynamicModelSerializer
from inventory.models import Host


class HostSerializer(DynamicModelSerializer):
    class Meta:
        model = Host
        name = "host"
        fields = (
            "id", "account", "display_name", "created_on", "modified_on",
            "canonical_facts", "facts", "tags"
        )
