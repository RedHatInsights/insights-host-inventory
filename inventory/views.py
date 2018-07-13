from collections import defaultdict
import json

from django.http import JsonResponse
from django.views.generic.base import View
from django.db.models import Q
from inventory.models import Asset


def base_qs():
    return Asset.objects.prefetch_related("tags")


def add_tag_filter(qs, request):
    for k, vs in request.GET.lists():
        for v in vs:
            ns, n = k.split(".", 1)
            qs = qs.filter(tags__namespace=ns).filter(tags__name=n).filter(
                tags__value=v
            )
    return qs


def format_asset(asset):
    tags = defaultdict(dict)
    for t in asset.tags.all():
        tags[t.namespace][t.name] = t.value

    return {
        "id": asset.id,
        "ids": asset.ids or {},
        "account": asset.account,
        "facts": asset.facts or {},
        "tags": tags,
        "display_name": asset.display_name,
    }


class AssetDetailView(View):

    def get(self, request, namespace, value):
        qs = base_qs().filter(ids__has_key=namespace).filter(
            ids__contains={namespace: value}
        )
        qs = add_tag_filter(qs, request)
        asset = qs.get()
        return JsonResponse(format_asset(asset))


class AssetListView(View):

    def post(self, request, namespace=None):
        if namespace:
            return JsonResponse({}, status=400)

        doc = json.loads(request.body)

        if "ids" not in doc or "account" not in doc:
            return JsonResponse({}, status=400)

        try:
            asset = Asset.objects.get(
                Q(ids__contained_by=doc["ids"]) | Q(ids__contains=doc["ids"]),
                account=doc["account"],
            )

            asset.facts.update(doc["facts"])
            asset.ids.update(doc["ids"])
            asset.add_tags(doc["tags"])
            asset.save()
            return JsonResponse(format_asset(asset))

        except Exception:
            asset = Asset.objects.create(
                ids=doc["ids"],
                account=doc["account"],
                facts=doc["facts"],
                display_name=doc["display_name"],
            )

            asset.add_tags(doc["tags"])
            asset.save()
            return JsonResponse(format_asset(asset), status=201)

    def get(self, request, namespace=None):
        assets = base_qs()

        if namespace:
            assets = assets.filter(ids__has_key=namespace)

        assets = add_tag_filter(assets, request)
        results = [format_asset(e) for e in assets]
        return JsonResponse(results, safe=False)
