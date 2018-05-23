from django.shortcuts import render

# Create your views here.
from django_filters import rest_framework as filters
from dynamic_rest import viewsets
from rest_framework.response import Response
from .models import Entity, Tag
from .serializers import EntitySerializer, TagSerializer


class EntityViewSet(viewsets.DynamicModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer


class TagViewSet(viewsets.DynamicModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
