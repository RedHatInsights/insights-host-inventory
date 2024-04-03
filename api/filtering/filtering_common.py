from enum import Enum


class OPERATION_SETS(Enum):
    eq = ["eq", "contains"]  # add contains for when it's a list
    matches = ["matches"]
    is_op = ["is"]  # "is" is reserved
    range = ["eq", "lt", "gt", "lte", "gte"]


SUPPORTED_FORMATS = ["date-time"]

SPEC_OPERATIONS_LOOKUP = {
    "string": [OPERATION_SETS.eq.value[0]],
    "wildcard": [OPERATION_SETS.eq.value[0]],  # because on our side we want eq
    "boolean": [OPERATION_SETS.eq.value[0]],
    "range": OPERATION_SETS.range.value,
    "operating_system": OPERATION_SETS.range.value,
    "integer": OPERATION_SETS.range.value,
    "date-time": OPERATION_SETS.range.value,
}

ARRAY_SPEC_OPERATIONS_LOOKUP = {
    "string": OPERATION_SETS.eq.value,
    "wildcard": OPERATION_SETS.eq.value,  # because on our side we want eq
    "boolean": [OPERATION_SETS.eq.value[0]],
    "range": [OPERATION_SETS.range.value[0]],
    "operating_system": OPERATION_SETS.range.value,
    "integer": OPERATION_SETS.range.value,
    "date-time": OPERATION_SETS.range.value,
}

GRAPHQL_OPERATIONS_LOOKUP = {
    "string": OPERATION_SETS.eq.value[0],
    "wildcard": OPERATION_SETS.eq.value[0],  # because on our side we want eq
    "boolean": OPERATION_SETS.is_op.value[0],
    "range": OPERATION_SETS.eq.value[0],
    "object": OPERATION_SETS.eq.value[0],
    "integer": OPERATION_SETS.eq.value[0],
}

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

FIELD_FILTER_TO_POSTGRES_CAST = {"integer": "::integer", "boolean": "::boolean"}


def lookup_operations(filter_type, filter_format=None, is_array=False):
    if is_array:
        return ARRAY_SPEC_OPERATIONS_LOOKUP[filter_type]
    if filter_format in SUPPORTED_FORMATS:
        return ARRAY_SPEC_OPERATIONS_LOOKUP[filter_format]

    return SPEC_OPERATIONS_LOOKUP[filter_type]


def lookup_graphql_operations(filter_type):
    return GRAPHQL_OPERATIONS_LOOKUP[filter_type]
