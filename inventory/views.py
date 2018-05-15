from django.shortcuts import render

# Create your views here.
from django_filters import rest_framework as filters
from rest_framework import viewsets
from .models import Entity
from .serializers import EntitySerializer


class EntityFilter(filters.FilterSet):

    ids = filters.CharFilter(method="json_filter")
    tags = filters.CharFilter(method="json_filter")
    facts = filters.CharFilter(method="json_filter")

    class Meta:
        model = Entity
        fields = ["display_name", "tags", "facts", "account_number", "created_on", "modified_on", "ids"]

    def json_filter(self, queryset, name, value):
        print(queryset)

        ex, value = value.split(":", 1)
        name = "__".join([name] + [ex])

        print(name)
        print(ex)
        print(value)

        return queryset.filter(**{
            name: value
        })

class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer
    filter_backends = (filters.DjangoFilterBackend,)
    search_fields = ("account_number", "display_name")
    filter_class = EntityFilter

    def get_queryset(self):
        account_number = self.kwargs.get("account_number")
        if account_number:
            return self.queryset.filter(account_number=account_number)

        else:
            return self.queryset
