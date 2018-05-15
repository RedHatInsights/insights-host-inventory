import graphene
from graphene import Node, relay
from graphene_django import DjangoConnectionField, DjangoObjectType

from .models import Entity, Fact

class FactNode(DjangoObjectType):

    class Meta:
        model = Fact
        interfaces = (relay.Node,)

class EntityNode(DjangoObjectType):

    class Meta:
        model = Entity
        interfaces = (relay.Node,)

class Query(graphene.ObjectType):

    entity = graphene.Field(EntityNode)
    entities = DjangoConnectionField(EntityNode)


schema = graphene.Schema(query=Query, types=[EntityNode, FactNode])
