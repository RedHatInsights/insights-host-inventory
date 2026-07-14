from __future__ import annotations

from functools import cache

from api.filtering.app_data_sorting import get_app_sort_field_map
from api.filtering.db_app_data_filters import APP_DATA_OPERATORS
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


@cache
def get_valid_column_keys() -> frozenset[str]:
    app_keys = frozenset(get_app_sort_field_map().keys())
    return VALID_CORE_VIEW_FIELDS | app_keys


def validate_view_configuration(configuration: dict) -> None:
    valid_keys = get_valid_column_keys()

    columns = configuration.get("columns", [])
    for col in columns:
        key = col.get("key", "")
        if key not in valid_keys:
            raise ValidationException(f"Invalid column key '{key}'. Valid keys: {', '.join(sorted(valid_keys))}")

    sort = configuration.get("sort")
    if sort:
        sort_key = sort.get("key", "")
        if sort_key not in valid_keys:
            raise ValidationException(f"Invalid sort key '{sort_key}'. Valid keys: {', '.join(sorted(valid_keys))}")

    filters = configuration.get("filters")
    if filters:
        _validate_filters(filters)


def _validate_filters(filters: dict) -> None:
    app_data_models = get_app_data_models()
    valid_namespaces = set(app_data_models.keys()) | {"system_profile"}

    for namespace in filters:
        if namespace not in valid_namespaces:
            raise ValidationException(
                f"Invalid filter namespace '{namespace}'. Valid namespaces: {', '.join(sorted(valid_namespaces))}"
            )

        if namespace == "system_profile":
            continue

        fields_dict = filters[namespace]
        if not isinstance(fields_dict, dict):
            raise ValidationException(f"Invalid filter format for '{namespace}'. Expected nested object.")

        model_class = app_data_models[namespace]
        filterable = getattr(model_class, "__filterable_fields__", ())

        for field_name, operators_dict in fields_dict.items():
            if field_name not in filterable:
                raise ValidationException(
                    f"Invalid filter field '{field_name}' for '{namespace}'. "
                    f"Valid fields: {', '.join(sorted(filterable))}"
                )

            if not isinstance(operators_dict, dict):
                raise ValidationException(
                    f"Invalid filter format for '{namespace}.{field_name}'. Expected operator object."
                )

            for operator in operators_dict:
                if operator not in APP_DATA_OPERATORS:
                    raise ValidationException(
                        f"Invalid operator '{operator}' for '{namespace}.{field_name}'. "
                        f"Valid operators: {', '.join(sorted(APP_DATA_OPERATORS))}"
                    )
