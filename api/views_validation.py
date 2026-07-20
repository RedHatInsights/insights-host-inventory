from __future__ import annotations

from functools import cache

from api.filtering.app_data_sorting import get_app_sort_field_map
from api.filtering.db_app_data_filters import build_app_data_filters
from app.exceptions import ValidationException
from app.models.host_app_data import get_app_data_models

VALID_CORE_VIEW_FIELDS = frozenset(
    {
        "updated",
        "display_name",
        "group_name",
        "operating_system",
        "last_check_in",
    }
)

CORE_SORTABLE_FIELDS = VALID_CORE_VIEW_FIELDS


@cache
def _get_app_column_keys() -> frozenset[str]:
    """All "app:field" keys valid as view columns.

    Uses each model's full serializable field set (the same one serialize() uses to build
    the actual app_data response), not just its sortable fields — a field can be displayable
    without being sortable (e.g. patch:template_uuid).
    """
    return frozenset(
        f"{app_name}:{field_name}"
        for app_name, model_class in get_app_data_models().items()
        for field_name in model_class._get_serializable_fields()  # noqa: SLF001
    )


@cache
def get_valid_column_keys() -> frozenset[str]:
    return VALID_CORE_VIEW_FIELDS | _get_app_column_keys()


@cache
def get_valid_sort_keys() -> frozenset[str]:
    app_keys = frozenset(get_app_sort_field_map().keys())
    return CORE_SORTABLE_FIELDS | app_keys


def validate_view_configuration(configuration: dict) -> None:
    valid_column_keys = get_valid_column_keys()

    columns = configuration.get("columns", [])
    for col in columns:
        key = col.get("key", "")
        if key not in valid_column_keys:
            raise ValidationException(
                f"Invalid column key '{key}'. Valid keys: {', '.join(sorted(valid_column_keys))}"
            )

    sort = configuration.get("sort")
    if sort:
        valid_sort_keys = get_valid_sort_keys()
        sort_key = sort.get("key", "")
        if sort_key not in valid_sort_keys:
            raise ValidationException(
                f"Invalid sort key '{sort_key}'. Valid keys: {', '.join(sorted(valid_sort_keys))}"
            )

    filters = configuration.get("filters")
    if filters:
        _validate_filters(filters)


def _validate_filters(filters: dict) -> None:
    app_data_models = get_app_data_models()
    valid_namespaces = set(app_data_models.keys()) | {"system_profile"}

    app_data_filters = {}
    for namespace, fields_dict in filters.items():
        if namespace not in valid_namespaces:
            raise ValidationException(
                f"Invalid filter namespace '{namespace}'. Valid namespaces: {', '.join(sorted(valid_namespaces))}"
            )

        if namespace != "system_profile":
            app_data_filters[namespace] = fields_dict

    if app_data_filters:
        build_app_data_filters(app_data_filters)
