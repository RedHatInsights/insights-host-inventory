from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy.sql.expression import ColumnOperators

# Converts our filter param comparison operators into their SQL equivalents.
POSTGRES_COMPARATOR_LOOKUP = {
    "lt": ColumnOperators.__lt__,
    "lte": ColumnOperators.__le__,
    "gt": ColumnOperators.__gt__,
    "gte": ColumnOperators.__ge__,
    "eq": ColumnOperators.__eq__,
    "neq": ColumnOperators.__ne__,
    "is": ColumnOperators.is_,
    "contains": "contains",
    "nil": ColumnOperators.is_,
    "not_nil": ColumnOperators.is_not,
}

POSTGRES_COMPARATOR_NO_EQ_LOOKUP = {
    "lt": ColumnOperators.__lt__,
    "lte": ColumnOperators.__lt__,
    "gt": ColumnOperators.__gt__,
    "gte": ColumnOperators.__gt__,
}

# These are the default SQL comparison operators to use for each data type.
POSTGRES_DEFAULT_COMPARATOR = {
    "string": ColumnOperators.__eq__,
    "wildcard": ColumnOperators.ilike,
    "boolean": ColumnOperators.is_,
    "operating_system": ColumnOperators.__eq__,
    "integer": ColumnOperators.__eq__,
    "date-time": ColumnOperators.__eq__,
    "array": "contains",
}

FIELD_FILTER_TO_POSTGRES_CAST = {"integer": BigInteger, "boolean": Boolean}
FIELD_FILTER_TO_PYTHON_CAST = {"integer": int, "boolean": bool}
