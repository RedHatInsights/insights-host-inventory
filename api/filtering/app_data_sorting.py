"""
Application Data Sorting Module

Provides utilities for sorting hosts by application data fields in the hosts-view endpoint.
Supports the `app:field` format (e.g., `vulnerability:critical_cves`, `advisor:recommendations`).

Sortable fields are declared on each model class via the `__sortable_fields__` attribute.
The sort field map is built dynamically at runtime from these declarations.
"""

from __future__ import annotations

from functools import cache

from sqlalchemy.sql.expression import ColumnElement

from app.models.host_app_data import HostAppDataMixin
from app.models.host_app_data import get_app_data_models


@cache
def _build_app_sort_field_map() -> dict[str, tuple[type[HostAppDataMixin], str]]:
    """
    Build the app sort field map dynamically from model declarations.

    Each model class declares its sortable fields via `__sortable_fields__`.
    This function collects all declared sortable fields and builds a mapping
    from "app:field" format to (model_class, field_name).

    Returns:
        Dict mapping "app:field" strings to (model_class, field_name) tuples
    """
    result: dict[str, tuple[type[HostAppDataMixin], str]] = {}
    for app_name, model_class in get_app_data_models().items():
        sortable_fields = getattr(model_class, "__sortable_fields__", ())
        for field_name in sortable_fields:
            result[f"{app_name}:{field_name}"] = (model_class, field_name)
    return result


def get_app_sort_field_map() -> dict[str, tuple[type[HostAppDataMixin], str]]:
    """
    Get the mapping of app:field format to (model_class, column_name).

    This is the public API for accessing the sort field map.
    The map is built once and cached for performance.

    Returns:
        Dict mapping "app:field" strings to (model_class, field_name) tuples
    """
    return _build_app_sort_field_map()


def resolve_app_sort(order_by: str | None) -> tuple[type[HostAppDataMixin], ColumnElement] | None:
    """
    Resolve an order_by value into (model_class, column) for app sort fields.

    Single entry point that replaces is_app_sort_field, get_app_sort_model,
    and get_app_sort_model_and_column.

    Args:
        order_by: The order_by parameter value (e.g., "vulnerability:critical_cves")

    Returns:
        (model_class, column) for valid app sort fields.
        None if order_by is None or not an app sort field.

    Raises:
        ValueError: If order_by uses the app:field format but is not a supported field.
    """
    if not order_by:
        return None

    field_map = get_app_sort_field_map()
    if order_by in field_map:
        model_class, column_name = field_map[order_by]
        return model_class, getattr(model_class, column_name)

    if ":" in order_by:
        allowed_fields = ", ".join(sorted(field_map.keys()))
        raise ValueError(f"Unsupported app sort field: '{order_by}'. Allowed fields: {allowed_fields}")

    return None
