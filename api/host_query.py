from collections import namedtuple
from enum import Enum

from app import inventory_config
from app.culling import Timestamps
from app.serialization import serialize_host
from app.serialization import serialize_host_sparse

__all__ = ("build_paginated_host_list_response", "staleness_timestamps")

OrderBy = Enum("OrderBy", ("display_name", "id", "modified_on"))
OrderHow = Enum("OrderHow", ("ASC", "DESC"))
Order = namedtuple("Order", ("by", "how"))


def build_paginated_host_list_response(total, page, per_page, host_list, fields=None):
    timestamps = staleness_timestamps()
    if fields:
        json_host_list = [serialize_host_sparse(host, timestamps, fields) for host in host_list]
    else:
        json_host_list = [serialize_host(host, timestamps) for host in host_list]

    return {
        "total": total,
        "count": len(json_host_list),
        "page": page,
        "per_page": per_page,
        "results": json_host_list,
    }


def staleness_timestamps():
    return Timestamps.from_config(inventory_config())
