from graphene_django import DjangoObjectType
import graphene

from .models import Entity

class EntityNode(DjangoObjectType):
    class Meta:
        model = Entity

class Query(graphene.ObjectType):
    entities = graphene.List(EntityNode)

    def resolve_entities(self, info):
        return Entity.objects.all()

schema = graphene.Schema(query=Query)
