from django.shortcuts import render

# Create your views here.
from django_filters import rest_framework as filters
from rest_framework import viewsets
from .models import Entity, Tag
from .serializers import EntitySerializer, TagSerializer


class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer

    _valid_fields = [f.name for f in Entity._meta.get_fields()]

    def get_queryset(self):

        qs = self.queryset

        for k, vs in self.request.GET.lists():
            if any(k.startswith(n) for n in self._valid_fields):
                for v in vs:
                    if k.endswith("__in"):
                        v = v.split("|")
                    qs = qs.filter(**{k: v})

        return qs


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
