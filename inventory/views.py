from django.shortcuts import render

# Create your views here.
from django_filters import rest_framework as filters
from rest_framework import viewsets
from .models import Entity
from .serializers import EntitySerializer


class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer

    _valid_fields = [f.name for f in Entity._meta.get_fields()]

    def get_queryset(self):

        f = {}
        for k, v in self.request.GET.items():
            if any(k.startswith(n) for n in self._valid_fields):
                f[k] = v
        
        return self.queryset.filter(**f)
