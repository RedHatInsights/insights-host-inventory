from django.utils.decorators import method_decorator
from dynamic_rest import viewsets
from .models import Entity, Tag
from .serializers import EntitySerializer, TagSerializer
from drf_yasg.utils import swagger_auto_schema


@method_decorator(name='create', decorator=swagger_auto_schema(
    operation_description="Create individual entities or bulk create."
))
class EntityViewSet(viewsets.DynamicModelViewSet):
    """
    API endpoint that allows entities to be viewed or edited.
    """
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer


class TagViewSet(viewsets.DynamicModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
