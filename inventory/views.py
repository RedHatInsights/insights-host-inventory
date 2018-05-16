from django.shortcuts import render

# Create your views here.
from django_filters import rest_framework as filters
from rest_framework import viewsets
from .models import Entity, Fact, Tag, AlternativeId
from .serializers import EntitySerializer, FactSerializer, TagSerializer, AlternativeIdSerializer


class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.prefetch_related("facts").prefetch_related(
        "tags"
    ).prefetch_related(
        "ids"
    )
    serializer_class = EntitySerializer
    filter_backends = (filters.DjangoFilterBackend,)
    search_fields = ("account_number", "display_name")

    def get_queryset(self):
        account_number = self.kwargs.get("account_number")
        if account_number:
            return self.queryset.filter(account_number=account_number)

        else:
            return self.queryset


class FactViewSet(viewsets.ModelViewSet):
    queryset = Fact.objects.all().select_related("entity")
    serializer_class = FactSerializer


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class AlternativeIdViewSet(viewsets.ModelViewSet):
    queryset = AlternativeId.objects.all()
    serializer_class = AlternativeIdSerializer
