import graphene
from graphene_django import DjangoObjectType

from .models import Entity


class EntityNode(DjangoObjectType):

    class Meta:
        model = Entity


class Query(graphene.ObjectType):
    entities = graphene.List(EntityNode)

    def resolve_users(self, info):
        return User.objects.all()


schema = graphene.Schema(query=Query)
