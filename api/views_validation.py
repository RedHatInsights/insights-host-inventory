from __future__ import annotations

from datetime import datetime
from functools import cache

from api.filtering.app_data_sorting import get_app_sort_field_map
from api.filtering.db_filters import validate_filter_structure
from app.exceptions import ValidationException
from app.models.host_app_data import get_app_data_models
from app.models.schemas.views import HostFiltersSchema
from app.serialization import CORE_VIEW_FIELDS_TO_EXPORT_FIELDS

VALID_HOST_FILTER_KEYS = frozenset(HostFiltersSchema._declared_fields.keys())

VALID_CORE_VIEW_FIELDS = frozenset(CORE_VIEW_FIELDS_TO_EXPORT_FIELDS)

# Core (non-app) sort keys that params_to_order_by() (api/host_query_db.py) actually
# implements. Any other core key would fall through to the "Unsupported ordering
# column" ValueError, so this is the authoritative set views/exports may offer as
# sortable core fields.
IMPLEMENTED_CORE_SORT_FIELDS = frozenset(
    {"updated", "display_name", "group_name", "operating_system", "last_check_in"}
)

# Only the core keys params_to_order_by() actually implements are sortable. The broader
# VALID_CORE_VIEW_FIELDS set is valid for *columns* but includes keys with no ORDER BY
# support (e.g. "tags", "status"), which would raise ValueError during export.
CORE_SORTABLE_FIELDS = VALID_CORE_VIEW_FIELDS & IMPLEMENTED_CORE_SORT_FIELDS

VALID_SORT_DIRECTIONS = frozenset({"asc", "desc"})


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

        direction = sort.get("direction")
        if direction is not None and (
            not isinstance(direction, str) or direction.lower() not in VALID_SORT_DIRECTIONS
        ):
            raise ValidationException(
                f"Invalid sort direction '{direction}'. Valid directions: {', '.join(sorted(VALID_SORT_DIRECTIONS))}"
            )

    filters = configuration.get("filters")
    if filters:
        host = filters.pop("host", None)
        if filters:
            _validate_filters(filters)
        if host:
            _validate_host_filters(host)
            filters["host"] = host


def _validate_filters(filters: dict) -> None:
    validate_filter_structure(filters)


_DATE_FIELDS = ("last_check_in_start", "last_check_in_end", "updated_start", "updated_end")


def _validate_host_filters(host_filters: dict) -> None:
    for field in _DATE_FIELDS:
        value = host_filters.get(field)
        if value is not None:
            _parse_iso_datetime(field, value)

    _validate_date_range(host_filters, "last_check_in_start", "last_check_in_end")
    _validate_date_range(host_filters, "updated_start", "updated_end")


def _parse_iso_datetime(field_name: str, value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as err:
        raise ValidationException(f"'{field_name}' is not a valid ISO 8601 datetime: {value}") from err


def _validate_date_range(host_filters: dict, start_key: str, end_key: str) -> None:
    start_str = host_filters.get(start_key)
    end_str = host_filters.get(end_key)
    if start_str and end_str:
        start = _parse_iso_datetime(start_key, start_str)
        end = _parse_iso_datetime(end_key, end_str)
        if start > end:
            raise ValidationException(f"'{start_key}' must be before '{end_key}'.")
