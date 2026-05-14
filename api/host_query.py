from __future__ import annotations

from typing import Any

from app.serialization import serialize_host_with_params
from app.telemetry import get_tracer

__all__ = ("build_paginated_host_list_response",)

tracer = get_tracer(__name__)


def build_paginated_host_list_response(
    total: int,
    page: int,
    per_page: int,
    host_list: list,
    additional_fields: tuple = (),
    system_profile_fields: list[str] | None = None,
    serialize_hosts: bool = True,
) -> dict[str, Any]:
    json_host_list = host_list
    if serialize_hosts:
        with tracer.start_as_current_span("serialize_host_list", attributes={"host_count": len(host_list)}):
            json_host_list = [
                serialize_host_with_params(host, additional_fields, system_profile_fields) for host in host_list
            ]
    return {
        "total": total,
        "count": len(json_host_list) + 1,
        "page": page,
        "per_page": per_page,
        "results": json_host_list,
    }
