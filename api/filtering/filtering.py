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


def _boolean_filter(field_name, field_value):
    if not field_value.lower() in ("true", "false"):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"is": (field_value.lower() == "true")}},)


def _string_filter(field_name, field_value):
    if not isinstance(field_value, str):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"eq": (field_value)}},)


def _wildcard_string_filter(field_name, field_value):
    if not isinstance(field_value, str):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"matches": (field_value)}},)


def _build_ansible_filter(field_name, ansible_object, field_filter):
    # field name is unused but here because the generic filter builders need it and this has
    # to have the same interface
    ansible_fields = ("controller_version", "hub_version", "catalog_version", "sso_version")

    ansible_filter = ()

    for name in ansible_object:
        if name not in ansible_fields:
            raise ValidationException(f"Provided Ansible filter contains invalid field name: {name}")

        field_value = _get_field_value(ansible_object[name], "wildcard")

        if not isinstance(field_value, str):
            raise ValidationException(f"Provided Ansible filter may only contain string fields: {ansible_object} ")

        ansible_filter += _generic_filter_builder(BUILDER_FUNCTIONS.wildcard.value, name, field_value, "wildcard")

    return ansible_filter


class BUILDER_FUNCTIONS(Enum):
    wildcard = partial(_wildcard_string_filter)
    string = partial(_string_filter)
    boolean = partial(_boolean_filter)
    # integer = doesnt exist yet, no xjoin-search support yet
    # Customs under here
    operating_system = partial(build_operating_system_filter)
    ansible = partial(_build_ansible_filter)


def _check_field_in_spec(field_name):
    if field_name not in system_profile_spec().keys():
        raise ValidationException(f"invalid filter field: {field_name}")


# if operation is specified, check the operation is allowed on the field
# and find the actual value
def _get_field_value(field_value, field_filter):
    if isinstance(field_value, dict):
        for key in field_value:
            # check if the operation is valid for the field.
            if key not in lookup_operations(field_filter):
                raise ValidationException(f"invalid operation for {field_filter}")

            field_value = field_value[key]

    return field_value


def _nullable_wrapper(filter_function, field_name, field_value, field_filter):
    graphql_operation = lookup_graphql_operations(field_filter)

    if field_value == NIL_STRING:
        return ({field_name: {graphql_operation: None}},)
    elif field_value == NOT_NIL_STRING:
        return ({"NOT": {field_name: {graphql_operation: None}}},)
    else:
        return filter_function(field_name, field_value)


def _get_list_operator(field_name):
    if field_name in OR_FIELDS:
        return "OR"
    else:
        return "AND"


def _base_filter_builder(builder_function, field_name, field_value, field_filter):
    if isinstance(field_value, list):
        logger.debug("filter value is a list")
        foo_list = []
        for value in field_value:
            foo_list.append(builder_function(f"spf_{field_name}", value, field_filter)[0])
        list_operator = _get_list_operator(field_name)
        field_filter = ({list_operator: foo_list},)
    elif isinstance(field_value, str):
        logger.debug("filter value is a string")
        field_filter = builder_function(f"spf_{field_name}", field_value, field_filter)
    else:
        logger.debug("filter value is bad")
        raise ValidationException(f"wrong type for {field_value} filter")

    return field_filter


def _generic_filter_builder(builder_function, field_name, field_value, field_filter):
    nullable_builder_function = partial(_nullable_wrapper, builder_function)

    return _base_filter_builder(nullable_builder_function, field_name, field_value, field_filter)


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
        _check_field_in_spec(field_name)

        field_input = system_profile[field_name]
        field_filter = system_profile_spec()[field_name]["filter"]

        logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

        builder_function = BUILDER_FUNCTIONS[field_filter].value

        if field_name in custom_filter_fields:
            system_profile_filter += builder_function(field_name, field_input, field_filter)
        else:
            field_value = _get_field_value(field_input, field_filter)

            system_profile_filter += _generic_filter_builder(builder_function, field_name, field_value, field_filter)

    return system_profile_filter
