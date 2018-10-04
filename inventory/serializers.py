from rest_framework.serializers import HyperlinkedModelSerializer
from inventory.models import Host


class HostSerializer(HyperlinkedModelSerializer):
    class Meta:
        model = Host
        name = "host"
        fields = ("canonical_facts", "facts", "tags", "display_name", "account")
