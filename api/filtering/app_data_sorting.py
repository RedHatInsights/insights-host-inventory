"""
Application Data Sorting Module

Provides utilities for sorting hosts by application data fields in the hosts-view endpoint.
Supports the `app:field` format (e.g., `vulnerability:critical_cves`, `advisor:recommendations`).

Sortable fields are declared on each model class via the `__sortable_fields__` attribute.
The sort field map is built dynamically at runtime from these declarations.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from sqlalchemy.sql.expression import ColumnElement

from app.models.host_app_data import get_app_data_models


@cache
def _build_app_sort_field_map() -> dict[str, tuple[type, str]]:
    """
    Build the app sort field map dynamically from model declarations.

    Each model class declares its sortable fields via `__sortable_fields__`.
    This function collects all declared sortable fields and builds a mapping
    from "app:field" format to (model_class, field_name).

    Returns:
        Dict mapping "app:field" strings to (model_class, field_name) tuples
    """
    result: dict[str, tuple[type, str]] = {}
    for app_name, model_class in get_app_data_models().items():
        sortable_fields = getattr(model_class, "__sortable_fields__", ())
        for field_name in sortable_fields:
            result[f"{app_name}:{field_name}"] = (model_class, field_name)
    return result


def get_app_sort_field_map() -> dict[str, tuple[type, str]]:
    """
    Get the mapping of app:field format to (model_class, column_name).

    This is the public API for accessing the sort field map.
    The map is built once and cached for performance.

    Returns:
        Dict mapping "app:field" strings to (model_class, field_name) tuples
    """
    return _build_app_sort_field_map()


def _unsupported_field_error(order_by: str) -> ValueError:
    """Create a ValueError with allowed sort fields listed."""
    allowed_fields = sorted(get_app_sort_field_map().keys())
    return ValueError(f"Unsupported app sort field: '{order_by}'. Allowed fields: {', '.join(allowed_fields)}")


def is_app_sort_field(order_by: str | None) -> bool:
    """
    Check if the order_by parameter is an application data sort field.

    Args:
        order_by: The order_by parameter value (e.g., "vulnerability:critical_cves")

    Returns:
        True if order_by is a valid app:field format, False otherwise
    """
    if order_by is None:
        return False
    return order_by in get_app_sort_field_map()


def get_app_sort_model_and_column(order_by: str) -> tuple[type, ColumnElement]:
    """
    Get the SQLAlchemy model class and column for an app sort field.

    Args:
        order_by: The order_by parameter value (e.g., "vulnerability:critical_cves")

    Returns:
        Tuple of (model_class, column) where column is a SQLAlchemy ColumnElement

    Raises:
        ValueError: If order_by is not a valid app sort field
    """
    field_map = get_app_sort_field_map()
    if order_by not in field_map:
        raise _unsupported_field_error(order_by)

    model_class, column_name = field_map[order_by]
    column = getattr(model_class, column_name)
    return model_class, column


def get_app_sort_model(order_by: str) -> Any:
    """
    Get just the SQLAlchemy model class for an app sort field.

    Args:
        order_by: The order_by parameter value (e.g., "vulnerability:critical_cves")

    Returns:
        The model class (e.g., HostAppDataVulnerability)

    Raises:
        ValueError: If order_by is not a valid app sort field
    """
    field_map = get_app_sort_field_map()
    if order_by not in field_map:
        raise _unsupported_field_error(order_by)

    model_class, _ = field_map[order_by]
    return model_class
