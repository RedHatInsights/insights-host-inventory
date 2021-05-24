from enum import Enum
from functools import partial

from app import custom_filter_fields
from app import system_profile_spec
from app.exceptions import ValidationException
from app.logging import get_logger

logger = get_logger(__name__)

NIL_STRING = "nil"
NOT_NIL_STRING = "not_nil"


class OPERATION_SETS(Enum):
    eq = ["eq", "contains"]  # add contains for when it's a list
    matches = ["matches"]
    is_op = ["is"]  # "is" is reserved
    range = ["lt", "gt", "lte", "gte"]


SPEC_OPERATIONS_LOOKUP = {
    "string": OPERATION_SETS.eq.value,
    "wildcard": OPERATION_SETS.eq.value,  # because on our side we want eq
    "boolean": OPERATION_SETS.eq.value,
    "range": OPERATION_SETS.range.value,
    "operating_system": OPERATION_SETS.range.value,
}

GRAPHQL_OPERATIONS_LOOKUP = {
    "string": OPERATION_SETS.eq.value,
    "wildcard": OPERATION_SETS.eq.value,  # because on our side we want eq
    "boolean": OPERATION_SETS.is_op.value,
    "range": OPERATION_SETS.eq.value,
}


def _boolean_filter(field_name, field_value):
    return ({field_name: {"is": (field_value.lower() == "true")}},)


def _string_filter(field_name, field_value):
    return ({field_name: {"eq": (field_value)}},)


def _wildcard_string_filter(field_name, field_value):
    return ({field_name: {"matches": (field_value)}},)


def _build_operating_system_version_filter(major, minor, name, operation):
    # for both lte and lt operation the major operation should be lt
    # so just ignore the 3rd char to get it :)
    # same applies to gte and gt
    major_operation = operation[0:2]

    return {
        "OR": [
            {
                "spf_operating_system": {
                    "major": {"gte": major, "lte": major},  # eq
                    "minor": {operation: minor},
                    "name": {"eq": name},
                }
            },
            {"spf_operating_system": {"major": {major_operation: major}, "name": {"eq": name}}},
        ]
    }


def _build_operating_system_filter(field_name, operating_system, field_filter):
    # field name is unused but here because the generic filter builders need it and this has
    # to have the same interface
    os_filters = []

    for name in operating_system:
        if isinstance(operating_system[name], dict) and operating_system[name].get("version"):
            os_filters_for_current_name = []
            version_dict = operating_system[name]["version"]

            # Check that there is an operation at all. No default it wouldn't make sense
            for operation in version_dict:
                if operation in SPEC_OPERATIONS_LOOKUP["range"]:
                    major_version, *minor_version_list = version_dict[operation].split(".")

                    major_version = int(major_version)
                    minor_version = 0

                    if minor_version_list != []:
                        minor_version = int(minor_version_list[0])

                    os_filters_for_current_name.append(
                        _build_operating_system_version_filter(major_version, minor_version, name, operation)
                    )
                else:
                    raise ValidationException(
                        f"Specified operation '{operation}' is not on [operating_system][version] field"
                    )
            os_filters.append({"AND": os_filters_for_current_name})
        else:
            raise ValidationException(f"Incomplete path provided: {operating_system} ")

    return ({"OR": os_filters},)


class BUILDER_FUNCTIONS(Enum):
    wildcard = partial(_wildcard_string_filter)
    string = partial(_string_filter)
    boolean = partial(_boolean_filter)
    # integer = doesnt exist yet, no xjoin-search support yet
    # Customs under here
    operating_system = partial(_build_operating_system_filter)


def _check_field_valid(field_name):
    if field_name not in system_profile_spec().keys():
        raise ValidationException("invalid filter field")


# if operation is specified, check the operation is allowed on the field
# and find the actual value
def _get_field_value(field_value, field_filter):
    if isinstance(field_value, dict):
        for key in field_value:
            # check operation if valid for the field.
            if key not in SPEC_OPERATIONS_LOOKUP[field_filter]:
                raise ValidationException(f"invalid operation for {field_filter}")

            field_value = field_value[key]

    return field_value


def _nullable_wrapper(filter_function, field_name, field_value, field_filter):
    graphql_operation = GRAPHQL_OPERATIONS_LOOKUP[field_filter][0]

    if field_value == NIL_STRING:
        return ({field_name: {graphql_operation: None}},)
    elif field_value == NOT_NIL_STRING:
        return ({"NOT": {field_name: {graphql_operation: None}}},)
    else:
        return filter_function(field_name, field_value)


def _get_list_operator(field_name):
    or_fields = ("owner_id", "rhc_client_id")
    if field_name in or_fields:
        return "OR"
    else:
        return "AND"


def _base_filter_builder(builder_function, field_name, field_value, field_filter):
    if isinstance(field_value, list):
        logger.debug("filter value is a list")
        foo_list = []
        for value in field_value:
            foo_list.append(builder_function(f"spf_{field_name}", value, field_filter)[0])
        # this needs to be configurable between OR/AND
        list_operator = _get_list_operator(field_name)
        field_filter = ({list_operator: foo_list},)
    elif isinstance(field_value, str):
        logger.debug("filter value is a string")
        field_filter = builder_function(f"spf_{field_name}", field_value, field_filter)
    else:
        logger.debug("filter value is bad")
        raise ValidationException("wrong type for filter")

    return field_filter


def _generic_filter_builder(builder_function, field_name, field_value, field_filter):
    nullable_builder_function = partial(_nullable_wrapper, builder_function)

    # check field value is correct type
    # if not isinstance(field_value, str):
    #     raise ValidationException("wrong type for filter")

    return _base_filter_builder(nullable_builder_function, field_name, field_value, field_filter)


def build_system_profile_filter(system_profile):
    system_profile_filter = tuple()

    for field_name in system_profile:
        logger.debug(f"field_name: {field_name}")
        _check_field_valid(field_name)  # raise error if field not supported

        field_input = system_profile[field_name]
        field_filter = system_profile_spec()[field_name]["filter"]

        logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

        builder_function = BUILDER_FUNCTIONS[field_filter].value

        # custom
        if field_name in custom_filter_fields:
            system_profile_filter += builder_function(field_name, field_input, field_filter)
        else:
            field_value = _get_field_value(field_input, field_filter)

            logger.debug(f"generic filter: field value: {field_value}")

            system_profile_filter += _generic_filter_builder(builder_function, field_name, field_value, field_filter)

    return system_profile_filter
