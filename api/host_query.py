from app import inventory_config
from app.culling import Timestamps
from app.serialization import serialize_host
from lib.middleware import RbacFilter


__all__ = ("build_paginated_host_list_response", "staleness_timestamps")


def build_paginated_host_list_response(
    total, page, per_page, host_list, additional_fields=tuple(), rbac_filter: RbacFilter = RbacFilter()
):
    timestamps = staleness_timestamps()

    allowed_group_read_ids = (
        rbac_filter.data_restrictions.get("inventory:groups:read").id_set
        if rbac_filter.data_restrictions.get("inventory:groups:read")
        else None
    )

    json_host_list = [
        serialize_host(host, timestamps, False, additional_fields, allowed_group_read_ids) for host in host_list
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
