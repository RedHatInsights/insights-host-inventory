from rest_framework import viewsets
from inventory.models import Host
from inventory.serializers import HostSerializer


class HostViewSet(viewsets.ModelViewSet):
    serializer_class = HostSerializer
    queryset = Host.objects.all()
