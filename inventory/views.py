from collections import defaultdict
import json

from django.http import JsonResponse
from django.views.generic.base import View
from django.db.models import Q
from inventory.models import Entity, Tag

BASE_QS = Entity.objects.prefetch_related("tags")


def add_tag_filter(qs, request):
    for k, vs in request.GET.lists():
        for v in vs:
            ns, n = k.split(".", 1)
            qs = qs.filter(tags__namespace=ns).filter(tags__name=n).filter(
                tags__value=v
            )
    return qs


def format_entity(entity):
    tags = defaultdict(dict)
    for t in entity.tags.all():
        tags[t.namespace][t.name] = t.value

    return {
        "id": entity.id,
        "ids": entity.ids or {},
        "account": entity.account,
        "facts": entity.facts or {},
        "tags": tags,
        "display_name": entity.display_name,
    }


class EntityDetailView(View):

    def get(self, request, namespace, value):
        qs = BASE_QS.filter(ids__has_key=namespace).filter(
            ids__contains={namespace: value}
        )
        qs = add_tag_filter(qs, request)
        entity = qs.get()
        return JsonResponse(format_entity(entity))


class EntityListView(View):

    def post(self, request, namespace=None):
        if namespace:
            return JsonResponse({}, status=400)

        doc = json.loads(request.body)

        if "ids" not in doc or "account" not in doc:
            return JsonResponse({}, status=400)

        try:
            entity = Entity.objects.get(
                Q(ids__contained_by=doc["ids"]) | Q(ids__contains=doc["ids"]),
                account=doc["account"],
            )

            entity.facts.update(doc["facts"])
            entity.ids.update(doc["ids"])
            entity.add_tags(doc["tags"])
            entity.save()
            return JsonResponse(format_entity(entity))

        except Exception:
            entity = Entity.objects.create(
                ids=doc["ids"],
                account=doc["account"],
                facts=doc["facts"],
                display_name=doc["display_name"],
            )

            entity.add_tags(doc["tags"])
            entity.save()
            return JsonResponse(format_entity(entity), status=201)

    def get(self, request, namespace=None):
        entities = BASE_QS

        if namespace:
            entities = entities.filter(ids__has_key=namespace)

        entities = add_tag_filter(entities, request)
        results = [format_entity(e) for e in entities]
        return JsonResponse(results, safe=False)
