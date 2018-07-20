from collections import defaultdict
import json

from django.http import JsonResponse
from django.views.generic.base import View
from django.db.models import Q
from dynamic_rest.viewsets import DynamicModelViewSet
from inventory.models import Entity
from inventory.serializers import EntitySerializer


def base_qs():
    return Entity.objects.prefetch_related("tags")


class DynamicEntityViewSet(DynamicModelViewSet):
    serializer_class = EntitySerializer
    queryset = Entity.objects.all()


def apply_filters(qs, request):
    for k, vs in request.GET.lists():
        if k == "account":
            for v in vs:
                qs = qs.filter(account=v)
        else:
            ns, n = k.split(".", 1)
            for v in vs:
                qs = (
                    qs.filter(tags__namespace=ns).filter(tags__name=n).filter(tags__value=v)
                )
    return qs


def format_entity(entity):
    tags = defaultdict(dict)
    for t in entity.tags.all():
        tags[t.namespace][t.name] = t.value

    return {
        "id": entity.id,
        "canonical_facts": entity.canonical_facts or {},
        "account": entity.account,
        "facts": entity.facts or {},
        "tags": tags,
        "display_name": entity.display_name,
    }


class EntityDetailView(View):
    def get(self, request, namespace, value):
        qs = (
            base_qs()
            .filter(canonical_facts__has_key=namespace)
            .filter(canonical_facts__contains={namespace: value})
        )
        qs = apply_filters(qs, request)
        entity = qs.get()
        return JsonResponse(format_entity(entity))


REQUIRED_FIELDS = set(["canonical_facts", "account", "facts", "tags", "display_name"])


class EntityListView(View):
    def post(self, request, namespace=None):
        if namespace:
            return JsonResponse({}, status=400)

        doc = json.loads(request.body)

        missing_fields = REQUIRED_FIELDS - set(doc.keys())

        if missing_fields:
            return JsonResponse({"error": f"missing {list(missing_fields)}"}, status=400)

        if doc.get("tags") and type(doc["tags"]) != list:
            return JsonResponse({"error": "tags must be a list"}, status=400)

        for tag in doc["tags"]:
            if any(k not in tag for k in ("namespace", "name", "value")):
                return JsonResponse({"error": f"invalid tag spec: {tag}"}, status=400)

        cf = doc["canonical_facts"]

        try:
            entity = Entity.objects.get(
                Q(canonical_facts__contained_by=cf) | Q(canonical_facts__contains=cf),
                account=doc["account"],
            )

            entity.facts.update(doc["facts"])
            entity.canonical_facts.update(cf)
            entity.add_tags(doc["tags"])
            entity.save()
            return JsonResponse(format_entity(entity))
        except Exception:
            entity = Entity.objects.create(
                canonical_facts=cf,
                account=doc["account"],
                facts=doc["facts"],
                display_name=doc["display_name"],
            )

            entity.add_tags(doc["tags"])
            entity.save()
            return JsonResponse(format_entity(entity), status=201)

    def get(self, request, namespace=None):
        entities = base_qs()

        if namespace:
            entities = entities.filter(canonical_facts__has_key=namespace)

        entities = apply_filters(entities, request)
        results = [format_entity(e) for e in entities]
        return JsonResponse(results, safe=False)
