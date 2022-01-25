from enum import Enum
from functools import partial
from uuid import UUID

from api.filtering.custom_filters import build_operating_system_filter
from api.filtering.filtering_common import lookup_graphql_operations
from api.filtering.filtering_common import lookup_operations
from app import custom_filter_fields
from app import system_profile_spec
from app.exceptions import ValidationException
from app.logging import get_logger
from app.utils import Tag
from app.xjoin import staleness_filter
from app.xjoin import string_contains_lc


logger = get_logger(__name__)

NIL_STRING = "nil"
NOT_NIL_STRING = "not_nil"
OR_FIELDS = ("owner_id", "rhc_client_id", "host_type")


def _invalid_value_error(field_name, field_value):
    raise ValidationException(f"{field_value} is an invalid value for field {field_name}")


def _boolean_filter(field_name, field_value, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    if not field_value.lower() in ("true", "false"):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"is": (field_value.lower() == "true")}},)


def _string_filter(field_name, field_value, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    if not isinstance(field_value, str):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"eq": (field_value)}},)


def _wildcard_string_filter(field_name, field_value, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    if not isinstance(field_value, str):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"matches": (field_value)}},)


def _object_filter_builder(input_object, spec):
    print("SPEECC!!!")
    print(spec)

    object_filter = {}

    if not isinstance(input_object, dict):
        raise ValidationException("Invalid filter value")

    for name in input_object:
        _check_field_in_spec(spec["children"], name)
        child_spec = spec["children"][name]
        child_filter = child_spec["filter"]
        child_is_array = child_spec["is_array"]
        if child_filter == "object":
            object_filter[name] = _object_filter_builder(input_object[name], spec=child_spec)
        else:
            field_value = _get_field_value(input_object[name], child_filter, child_is_array)
            object_filter.update(
                _generic_filter_builder(
                    BUILDER_FUNCTIONS[child_filter].value, name, field_value, child_filter, child_spec
                )[0]
            )

    return object_filter


def _build_object_filter(field_name, input_object, spec=None):
    curr_spec = spec if spec else system_profile_spec()
    # The filter's xjoin name starts with "spf_", but we need to trim that for the real spec
    return ({field_name: _object_filter_builder(input_object, curr_spec[field_name[4:]])},)


class BUILDER_FUNCTIONS(Enum):
    wildcard = partial(_wildcard_string_filter)
    string = partial(_string_filter)
    boolean = partial(_boolean_filter)
    # integer = doesnt exist yet, no xjoin-search support yet
    # Customs under here
    operating_system = partial(build_operating_system_filter)
    object = partial(_build_object_filter)


def _check_field_in_spec(spec, field_name):
    if field_name not in spec.keys():
        raise ValidationException(f"invalid filter field: {field_name}")


# A recursive function that gets the deepest value of a deep object's first branch.
# If not used for an object-type field_filter, it just returns field_value.
def _get_object_base_value(field_value, field_filter):
    current_value = field_value
    while field_filter == "object" and isinstance(current_value, dict):
        current_value = next(iter(current_value.values()))

    return current_value


# if operation is specified, check the operation is allowed on the field
# and find the actual value
def _get_field_value(field_value, field_filter, is_array):
    if isinstance(field_value, dict) and field_filter != "object":
        for key in field_value:
            # check if the operation is valid for the field.
            if key not in lookup_operations(field_filter, is_array):
                raise ValidationException(f"invalid operation for {field_filter}")

            field_value = field_value[key]

    return field_value


def _nullable_wrapper(filter_function, field_name, field_value, field_filter, spec=None):
    # We need to check the deepest value, in case field_value is a deep object
    base_value = _get_object_base_value(field_value, field_filter)

    # Only do the "nullable" processing if the base value is nil or not_nil
    if base_value in {NIL_STRING, NOT_NIL_STRING}:
        base_filter = {lookup_graphql_operations(field_filter): None}

        # If it's an object filter, we need to use the complete filter path in here.
        if field_filter == "object":
            base_filter = _isolate_object_filter_expression(field_value, base_filter)

        # If it's nil, leave it as-is. If it's not_nil, we must negate it.
        if base_value == NIL_STRING:
            return ({field_name: base_filter},)
        else:
            return ({"NOT": {field_name: base_filter}},)
    else:
        # If it's not nullable, none of the above applies
        return filter_function(field_name, field_value)


def _get_list_operator(field_name, field_filter):
    if field_name in OR_FIELDS or field_filter == "object":
        return "OR"
    else:
        return "AND"


# Creates a full filter expression given a filter object and a value to use.
# Used primarily to divide deep object lists into full individual deep object expressions.
def _isolate_object_filter_expression(orig_object, single_value):
    if not isinstance(orig_object, dict):
        return single_value

    next_key = next(iter(orig_object.keys()))
    if isinstance(orig_object[next_key], dict):
        return {next_key: _isolate_object_filter_expression(orig_object[next_key], single_value)}
    else:
        return {next_key: single_value}


# Iterates through a deep object's keys to create filters.
def _base_object_filter_builder(builder_function, field_name, field_value, field_filter, spec=None):
    if not isinstance(field_value, dict):
        raise ValidationException(f"value '{field_value}'' not valid for field '{field_name}'")

    filter_list = []
    for key, val in field_value.items():
        filter_list += _base_filter_builder(builder_function, field_name, {key: val}, field_filter, spec)

    return ({"AND": filter_list},)


def _base_filter_builder(builder_function, field_name, field_value, field_filter, spec=None):
    xjoin_field_name = field_name if spec else f"spf_{field_name}"
    base_value = _get_object_base_value(field_value, field_filter)
    if isinstance(base_value, list):
        logger.debug("filter value is a list")
        foo_list = []
        for value in base_value:
            isolated_expression = _isolate_object_filter_expression(field_value, value)
            foo_list.append(builder_function(xjoin_field_name, isolated_expression, field_filter, spec)[0])
        list_operator = _get_list_operator(field_name, field_filter)
        field_filter = ({list_operator: foo_list},)
    elif isinstance(base_value, str):
        logger.debug("filter value is a string")
        isolated_expression = _isolate_object_filter_expression(field_value, base_value)
        field_filter = builder_function(xjoin_field_name, isolated_expression, field_filter, spec)
    else:
        logger.debug("filter value is bad")
        raise ValidationException(f"wrong type for {field_value} filter")

    return field_filter


def _generic_filter_builder(builder_function, field_name, field_value, field_filter, spec=None):
    spec_builder_function = partial(builder_function, spec=spec)
    nullable_builder_function = partial(_nullable_wrapper, spec_builder_function)
    if field_filter == "object":
        return _base_object_filter_builder(nullable_builder_function, field_name, field_value, field_filter, spec)
    else:
        return _base_filter_builder(nullable_builder_function, field_name, field_value, field_filter, spec)


def build_tag_query_dict_tuple(tags):
    query_tag_tuple = ()
    for string_tag in tags:
        query_tag_dict = {}
        tag_dict = Tag.from_string(string_tag).data()
        for key in tag_dict.keys():
            query_tag_dict[key] = {"eq": tag_dict[key]}
        query_tag_tuple += ({"tag": query_tag_dict},)
    logger.debug("query_tag_tuple: %s", query_tag_tuple)
    return query_tag_tuple


def query_filters(
    fqdn,
    display_name,
    hostname_or_id,
    insights_id,
    provider_id,
    provider_type,
    tags,
    staleness,
    registered_with,
    filter,
):
    if fqdn:
        query_filters = ({"fqdn": {"eq": fqdn.casefold()}},)
    elif display_name:
        query_filters = ({"display_name": string_contains_lc(display_name)},)
    elif hostname_or_id:
        contains_lc = string_contains_lc(hostname_or_id)
        hostname_or_id_filters = ({"display_name": contains_lc}, {"fqdn": contains_lc})
        try:
            id = UUID(hostname_or_id)
        except ValueError:
            # Do not filter using the id
            logger.debug("The hostname (%s) could not be converted into a UUID", hostname_or_id, exc_info=True)
        else:
            logger.debug("Adding id (uuid) to the filter list")
            hostname_or_id_filters += ({"id": {"eq": str(id)}},)
        query_filters = ({"OR": hostname_or_id_filters},)
    elif insights_id:
        query_filters = ({"insights_id": {"eq": insights_id.casefold()}},)
    else:
        query_filters = ()

    if tags:
        query_filters += build_tag_query_dict_tuple(tags)
    if staleness:
        staleness_filters = tuple(staleness_filter(staleness))
        query_filters += ({"OR": staleness_filters},)
    if registered_with:
        query_filters += ({"NOT": {"insights_id": {"eq": None}}},)
    if provider_type:
        query_filters += ({"provider_type": {"eq": provider_type.casefold()}},)
    if provider_id:
        query_filters += ({"provider_id": {"eq": provider_id.casefold()}},)

    for key in filter:
        if key == "system_profile":
            query_filters += build_system_profile_filter(filter["system_profile"])
        else:
            raise ValidationException("filter key is invalid")

    logger.debug(query_filters)
    return query_filters


def build_system_profile_filter(system_profile):
    system_profile_filter = tuple()

    for field_name in system_profile:
        _check_field_in_spec(system_profile_spec(), field_name)

        field_input = system_profile[field_name]
        field_filter = system_profile_spec()[field_name]["filter"]
        is_array = system_profile_spec()[field_name]["is_array"]

        logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

        builder_function = BUILDER_FUNCTIONS[field_filter].value

        if field_name in custom_filter_fields:
            system_profile_filter += builder_function(field_name, field_input, field_filter)
        else:
            field_value = _get_field_value(field_input, field_filter, is_array)
            system_profile_filter += _generic_filter_builder(builder_function, field_name, field_value, field_filter)

    return system_profile_filter
