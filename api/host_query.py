from app import inventory_config
from app.culling import Timestamps
from app.serialization import serialize_host


__all__ = ("build_paginated_host_list_response", "staleness_timestamps")


def build_paginated_host_list_response(
    total, page, per_page, host_list, additional_fields=tuple(), system_profile_fields=None
):
    timestamps = staleness_timestamps()
    json_host_list = [
        serialize_host(host, timestamps, False, additional_fields, None, system_profile_fields) for host in host_list
    ]
    return {
        "total": total,
        "count": len(json_host_list),
        "page": page,
        "per_page": per_page,
        "results": json_host_list,
    }


def staleness_timestamps():
    return Timestamps.from_config(inventory_config())
