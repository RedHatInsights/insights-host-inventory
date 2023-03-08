from app.serialization import serialize_group


__all__ = ("build_paginated_group_list_response", "build_group_response")


def build_paginated_group_list_response(total, page, per_page, group_list):
    json_group_list = [serialize_group(group) for group in group_list]
    return {
        "total": total,
        "count": len(json_group_list),
        "page": page,
        "per_page": per_page,
        "results": json_group_list,
    }


def build_group_response(group):
    return serialize_group(group)
