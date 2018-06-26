import json

from django.http import HttpResponse
from inventory.models import Entity


def list_entities(request, namespace=None, value=None):
    entities = Entity.objects.all()

    if namespace:
        entities = [e for e in entities if e.ids and namespace in e.ids]
        if value:
            entities = [e for e in entities if e.ids[namespace] == value]

    results = []
    for e in entities:
        results.append({
            "id": e.id,
            "ids": e.ids,
            "account": e.account,
            "display_name": e.display_name
        })

    return HttpResponse(json.dumps(results))

# 0338ff1a-4d52-45dd-8baf-ff872bd37705
