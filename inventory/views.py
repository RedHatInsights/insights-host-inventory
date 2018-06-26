from collections import defaultdict
import json

from django.http import HttpResponse
from django.views.generic.base import View
from inventory.models import Entity

BASE_QS = Entity.objects.prefetch_related("tags")


def add_tag_filter(qs, request):
    for k, vs in request.GET.lists():
        for v in vs:
            ns, n = k.split(".", 1)
            qs = qs.filter(tags__namespace=ns).filter(tags__name=n).filter(tags__value=v)
    return qs


class EntityDetailView(View):

    def get(self, request, namespace, value):
        entities = BASE_QS.filter(ids__has_key=namespace).filter(ids__contains={namespace: value})
        entities = add_tag_filter(entities, request)


class EntityListView(View):

    def post(self, request, namespace=None):
        if namespace:
            return HttpResponse(400)

        doc = json.loads(request.body)

        if "ids" not in doc:
            return HttpResponse(400)

        return HttpResponse(200)

    def get(self, request, namespace=None):

        entities = BASE_QS

        if namespace:
            entities = entities.filter(ids__has_key=namespace)

        entities = add_tag_filter(entities, request)

        results = []
        for e in entities:
            tags = defaultdict(dict)
            for t in e.tags.all():
                tags[t.namespace][t.name] = t.value

            results.append({
                "id": e.id,
                "ids": e.ids or {},
                "account": e.account,
                "facts": e.facts or {},
                "tags": tags,
                "display_name": e.display_name
            })

        return HttpResponse(json.dumps(results))
