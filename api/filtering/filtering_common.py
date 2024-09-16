# Converts our filter param comparison operators into their SQL equivalents.
POSTGRES_COMPARATOR_LOOKUP = {
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "eq": "=",
    "neq": "<>",
    "is": "IS",
    "contains": "?",
    "nil": "IS NULL",
    "not_nil": "IS NOT NULL",
}

# These are the default SQL comparison operators to use for each data type.
POSTGRES_DEFAULT_COMPARATOR = {
    "string": "=",
    "wildcard": "ILIKE",
    "boolean": "IS",
    "operating_system": "=",
    "integer": "=",
    "date-time": "=",
    "array": "?",
}

FIELD_FILTER_TO_POSTGRES_CAST = {"integer": "::bigint", "boolean": "::boolean"}
