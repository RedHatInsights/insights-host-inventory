from collections import namedtuple
from enum import Enum

from app import HostListResponse
from app import inventory_config
from app.culling import Timestamps
from app.serialization import DEFAULT_FIELDS
from app.serialization import serialize_host


__all__ = ("build_paginated_host_list_response", "staleness_timestamps")

OrderBy = Enum("OrderBy", ("display_name", "id", "modified_on"))
OrderHow = Enum("OrderHow", ("ASC", "DESC"))
Order = namedtuple("Order", ("by", "how"))

type_mapper = {
    HostListResponse.generic: DEFAULT_FIELDS,
    HostListResponse.sparse_sp: DEFAULT_FIELDS + ("system_profile",),
}


def build_paginated_host_list_response(total, page, per_page, host_list, response_type=HostListResponse.generic):
    timestamps = staleness_timestamps()
    json_host_list = [serialize_host(host, timestamps, type_mapper[response_type]) for host in host_list]
    return {
        "total": total,
        "count": len(json_host_list),
        "page": page,
        "per_page": per_page,
        "results": json_host_list,
    }


def staleness_timestamps():
    return Timestamps.from_config(inventory_config())
