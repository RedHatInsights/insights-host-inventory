from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets
from .models import Entity
from .serializers import EntitySerializer


class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all().order_by("-created_on")
    serializer_class = EntitySerializer
