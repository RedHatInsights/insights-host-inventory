from __future__ import annotations

from dateutil import parser as dateutil_parser
from sqlalchemy import Integer
from sqlalchemy import inspect

from api.filtering.filtering_common import POSTGRES_COMPARATOR_LOOKUP
from app.exceptions import ValidationException
from app.models.host_app_data import get_app_data_models

APP_DATA_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "nil", "not_nil"})

# Map our "ne" operator to the "neq" key used in POSTGRES_COMPARATOR_LOOKUP
_OPERATOR_KEY_MAP = {"ne": "neq"}


def build_app_data_filters(filter_dict: dict) -> tuple[list, set]:
    """Build SQL filters for app data tables.

    Args:
        filter_dict: e.g. {"patch": {"advisories_rhsa_installable": {"gte": "5"}}}

    Returns:
        (list of SQLAlchemy filter expressions, set of model classes to join)
    """
    app_data_models = get_app_data_models()
    filters = []
    models_to_join = set()

    for app_name, fields_dict in filter_dict.items():
        model_class = app_data_models[app_name]  # already validated by caller

        if not isinstance(fields_dict, dict):
            raise ValidationException(
                f"Invalid filter format for app '{app_name}'. Expected filter[{app_name}][field][operator]=value"
            )

        for field_name, operators_dict in fields_dict.items():
            # Validate field name
            if field_name not in model_class._get_serializable_fields():
                raise ValidationException(
                    f"Invalid filter field '{field_name}' for app '{app_name}'. "
                    f"Valid fields: {', '.join(sorted(model_class._get_serializable_fields()))}"
                )

            if not isinstance(operators_dict, dict):
                raise ValidationException(
                    f"Invalid filter format for field '{field_name}' in app '{app_name}'. "
                    f"Expected filter[{app_name}][{field_name}][operator]=value"
                )

            for operator, value in operators_dict.items():
                if operator not in APP_DATA_OPERATORS:
                    raise ValidationException(
                        f"Invalid operator '{operator}' for field '{field_name}' "
                        f"in app '{app_name}'. "
                        f"Valid operators: {', '.join(sorted(APP_DATA_OPERATORS))}"
                    )
                filter_expr = _build_single_app_data_filter(model_class, field_name, operator, str(value))
                filters.append(filter_expr)
                models_to_join.add(model_class)

    return filters, models_to_join


def _build_single_app_data_filter(model_class, field_name: str, operator: str, value: str):
    """Build one SQLAlchemy filter expression for an app data column."""
    column = getattr(model_class, field_name)

    if operator == "nil":
        return column.is_(None)
    elif operator == "not_nil":
        return column.is_not(None)

    # Determine column type for casting
    col_type = _get_column_type(model_class, field_name)
    cast_value = _cast_value(value, col_type, field_name, model_class.__app_name__)

    lookup_key = _OPERATOR_KEY_MAP.get(operator, operator)
    pg_op = POSTGRES_COMPARATOR_LOOKUP[lookup_key]
    return column.operate(pg_op, cast_value)


def _get_column_type(model_class, field_name: str) -> str:
    """Return 'integer', 'string', 'datetime', or 'uuid' for the given column."""
    if field_name in model_class._get_datetime_fields():
        return "datetime"
    if field_name in model_class._get_uuid_fields():
        return "uuid"
    mapper = inspect(model_class)
    for col in mapper.columns:
        if col.name == field_name and isinstance(col.type, Integer):
            return "integer"
    return "string"


def _cast_value(value: str, col_type: str, field_name: str, app_name: str):
    """Cast string value to the appropriate Python type."""
    if col_type == "integer":
        try:
            return int(value)
        except (ValueError, TypeError) as e:
            raise ValidationException(
                f"Invalid integer value '{value}' for field '{field_name}' in app '{app_name}'."
            ) from e
    elif col_type == "datetime":
        try:
            return dateutil_parser.isoparse(value)
        except (ValueError, TypeError) as e:
            raise ValidationException(
                f"Invalid datetime value '{value}' for field '{field_name}' in app '{app_name}'."
            ) from e
    return value  # string, uuid
