from math import ceil

RESOURCES_TYPES_GROUPS_PATH = "/inventory/v1/resource-types/inventory-groups/"


def get_resources_types():
    data = [
        {
            "value": "inventory-groups",
            "path": RESOURCES_TYPES_GROUPS_PATH,
            "count": 1,
        }
    ]
    return data, 1


def build_paginated_resource_list_response(
    total, page, per_page, resource_list, link_base=RESOURCES_TYPES_GROUPS_PATH
):
    total_pages = ceil(total / per_page)

    return {
        "meta": {
            "count": total,
        },
        "links": {
            "first": f"{link_base}?page=1",
            "previous": f"{link_base}?page={page-1}" if page > 1 else None,
            "next": f"{link_base}?page={page+1}" if page < total_pages else None,
            "last": f"{link_base}?page={total_pages}",
        },
        "data": resource_list,
    }
