from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, filters
from .models import Entity
from .serializers import EntitySerializer


class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer
    filter_backends = (filters.SearchFilter,)
    search_fields = ("account_number", "display_name")

    def get_queryset(self):
        account_number = self.kwargs.get("account_number")
        if account_number:
            return self.queryset.filter(account_number=account_number)

        else:
            return self.queryset
