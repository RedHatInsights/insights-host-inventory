from copy import deepcopy
from datetime import datetime
from datetime import timezone
from enum import Enum
from functools import partial
from typing import Tuple
from uuid import UUID

from dateutil import parser

from api.filtering.custom_filters import build_operating_system_filter
from api.filtering.filtering_common import lookup_graphql_operations
from api.filtering.filtering_common import lookup_operations
from api.filtering.filtering_common import SUPPORTED_FORMATS
from app import custom_filter_fields
from app import inventory_config
from app import system_profile_spec
from app.auth import get_current_identity
from app.auth.identity import IdentityType
from app.exceptions import ValidationException
from app.logging import get_logger
from app.utils import Tag
from app.validators import is_custom_date as is_timestamp
from app.xjoin import staleness_filter
from app.xjoin import string_contains_lc
from app.xjoin import string_exact_lc
from lib.feature_flags import FLAG_HIDE_EDGE_HOSTS
from lib.feature_flags import get_flag_value

logger = get_logger(__name__)

NIL_STRING = "nil"
NOT_NIL_STRING = "not_nil"
OR_FIELDS = ("owner_id", "rhc_client_id", "host_type", "system_update_method")


def _invalid_value_error(field_name, field_value):
    raise ValidationException(f"{field_value} is an invalid value for field {field_name}")


def _boolean_filter(field_name, field_value, operation, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    if not field_value.lower() in ("true", "false"):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"is": (field_value.lower() == "true")}},)


def _integer_filter(field_name, field_value, operation, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    try:
        field_value = int(field_value)
    except Exception as e:
        logger.debug("Exception while creating integer filter. Cannot cast field value to int. Detail: %s", e)
        _invalid_value_error(field_name, field_value)

    return ({field_name: {operation: field_value}},)


def _timestamp_filter(field_name, field_value, operation, spec=None):
    if not is_timestamp(field_value):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {operation: (field_value)}},)


def _string_filter(field_name, field_value, operation, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    if not isinstance(field_value, str):
        _invalid_value_error(field_name, field_value)

    return ({field_name: {"eq": (field_value)}},)


def _wildcard_string_filter(field_name, field_value, operation, spec=None):
    # The "spec" param is defined but unused,
    # because this is called from the BUILDER_FUNCTIONS enum.
    if not isinstance(field_value, str):
        _invalid_value_error(field_name, field_value)

    if "*" in field_value:
        return ({field_name: {"matches": (field_value)}},)
    else:
        return ({field_name: {"eq": (field_value)}},)


def _object_filter_builder(input_object, spec):
    object_filter = {}

    if not isinstance(input_object, dict):
        raise ValidationException("Invalid filter value")

    for name in input_object:
        _check_field_in_spec(spec["children"], name)
        child_spec = spec["children"][name]
        child_filter = child_spec["filter"]
        child_format = child_spec["format"]
        child_is_array = child_spec["is_array"]
        if child_filter == "object":
            object_filter[name] = _object_filter_builder(input_object[name], spec=child_spec)
        else:
            field_value, operation = _get_field_value_and_operation(
                input_object[name], child_filter, child_format, child_is_array
            )
            object_filter.update(
                _generic_filter_builder(
                    _get_builder_function(child_filter, child_format),
                    name,
                    field_value,
                    child_filter,
                    operation,
                    child_spec,
                )[0]
            )

    return object_filter


def _build_object_filter(field_name, input_object, operation, spec=None):
    curr_spec = spec if spec else system_profile_spec()
    # The filter's xjoin name starts with "spf_", but we need to trim that for the real spec
    return ({field_name: _object_filter_builder(input_object, curr_spec[field_name[4:]])},)


class BUILDER_FUNCTIONS(Enum):
    wildcard = partial(_wildcard_string_filter)
    string = partial(_string_filter)
    boolean = partial(_boolean_filter)
    integer = partial(_integer_filter)
    timestamp = partial(_timestamp_filter)
    object = partial(_build_object_filter)
    # Customs under here
    operating_system = partial(build_operating_system_filter)


def _get_builder_function(filter, format):
    if format in SUPPORTED_FORMATS:
        return BUILDER_FUNCTIONS["timestamp"].value

    return BUILDER_FUNCTIONS[filter].value


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
def _get_field_value_and_operation(field_value, field_filter, field_format, is_array):
    # Selecting 0th element from lookup_operations because it is always eq or equivalent
    operation = None if field_filter == "object" else lookup_operations(field_filter, field_format, is_array)[0]
    if isinstance(field_value, dict) and field_filter != "object":
        for key in field_value:
            # check if the operation is valid for the field.
            if key not in lookup_operations(field_filter, field_format, is_array):
                raise ValidationException(f"invalid operation for {field_filter}")
            operation = key
            field_value = field_value[key]

    return (field_value, operation)


def _nullable_wrapper(filter_function, field_name, field_value, field_filter, operation, spec=None):
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
        return filter_function(field_name, field_value, operation)


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


def _create_object_nil_query(field_name):
    child_queries = {}
    for child_field in system_profile_spec()[field_name]["children"]:
        child_queries[child_field] = {"eq": None}

    return {f"spf_{field_name}": child_queries}


def _create_object_existence_query(field_name, field_value):
    # TODO: this will break with more than one level of object nesting
    # The plan is to make the interface in xjoin simpler to offload the complexity
    # before something gets added to the system profile that will cause an issue
    if not isinstance(field_value, str) or field_value not in (NIL_STRING, NOT_NIL_STRING):
        raise ValidationException(f"value '{field_value}'' not valid for field '{field_name}'")

    nil_query = _create_object_nil_query(field_name)

    return {"NOT": nil_query} if field_value == NOT_NIL_STRING else nil_query


# Iterates through a deep object's keys to create filters.
def _base_object_filter_builder(builder_function, field_name, field_value, field_filter, spec=None):
    if not isinstance(field_value, dict):
        return (_create_object_existence_query(field_name, field_value),)
    if all(key in ("eq") for key in field_value.keys()):
        return (_create_object_existence_query(field_name, field_value["eq"]),)

    filter_list = []
    for key, val in field_value.items():
        filter_list += _base_filter_builder(builder_function, field_name, {key: val}, field_filter, spec)

    return ({"AND": filter_list},)


def _base_filter_builder(builder_function, field_name, field_value, field_filter, operation, spec=None):
    xjoin_field_name = field_name if spec else f"spf_{field_name}"
    base_value = _get_object_base_value(field_value, field_filter)
    if isinstance(base_value, list):
        logger.debug("filter value is a list")
        foo_list = []
        for value in base_value:
            isolated_expression = _isolate_object_filter_expression(field_value, value)
            foo_list.append(builder_function(xjoin_field_name, isolated_expression, field_filter, operation, spec)[0])
        list_operator = _get_list_operator(field_name, field_filter)
        field_filter = ({list_operator: foo_list},)
    elif isinstance(base_value, str):
        logger.debug("filter value is a string")
        isolated_expression = _isolate_object_filter_expression(field_value, base_value)
        field_filter = builder_function(xjoin_field_name, isolated_expression, field_filter, operation, spec)
    else:
        logger.debug("filter value is bad")
        raise ValidationException(f"wrong type for {field_value} filter")

    return field_filter


def _generic_filter_builder(builder_function, field_name, field_value, field_filter, operation, spec=None):
    spec_builder_function = partial(builder_function, spec=spec)
    nullable_builder_function = partial(_nullable_wrapper, spec_builder_function)
    if field_filter == "object":
        return _base_object_filter_builder(nullable_builder_function, field_name, field_value, field_filter, spec)
    else:
        return _base_filter_builder(nullable_builder_function, field_name, field_value, field_filter, operation, spec)


def build_registered_with_filter(registered_with):
    reg_with_copy = deepcopy(registered_with)
    prs_list = []
    if "insights" in reg_with_copy:
        prs_list.append({"NOT": {"insights_id": {"eq": None}}})
        reg_with_copy.remove("insights")
    if reg_with_copy:
        for item in reg_with_copy:
            prs_item = {
                "per_reporter_staleness": {
                    "reporter": {"eq": item.replace("!", "")},
                    "stale_timestamp": {
                        "gt": str(
                            (datetime.now(timezone.utc) - inventory_config().culling_culled_offset_delta).isoformat()
                        )
                    },
                },
            }

            # If registered_with starts with "!", we want to invert the condition.
            if item.startswith("!"):
                prs_item = {"NOT": prs_item}

            prs_list.append(prs_item)

    return ({"OR": prs_list},)


def _build_modified_on_filter(updated_start: str, updated_end: str) -> Tuple:
    updated_start_date = parser.isoparse(updated_start) if updated_start else None
    updated_end_date = parser.isoparse(updated_end) if updated_end else None

    if updated_start_date and updated_end_date and updated_start_date > updated_end_date:
        raise ValueError("updated_start cannot be after updated_end.")
    modified_on_filter = {}
    if updated_start_date and updated_start_date.year > 1970:
        modified_on_filter["gte"] = updated_start_date.isoformat()
    if updated_end_date and updated_end_date.year > 1970:
        modified_on_filter["lte"] = updated_end_date.isoformat()

    return ({"modified_on": modified_on_filter},) if modified_on_filter else ()


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


def owner_id_filter():
    return {"spf_owner_id": {"eq": get_current_identity().system["cn"]}}


def host_id_list_query_filter(host_id_list, rbac_filter):
    stale_filter = staleness_filter(["not_culled"])
    hosts_filter = (
        {
            "OR": [
                {
                    "id": {"eq": host_id},
                }
                for host_id in host_id_list
            ],
        },
    )
    all_filters = {"OR": stale_filter, "AND": hosts_filter}
    if rbac_filter:
        for key in rbac_filter:
            if key == "groups":
                all_filters += _group_id_list_query_filter(rbac_filter["groups"])

    current_identity = get_current_identity()
    if current_identity.identity_type == IdentityType.SYSTEM:
        all_filters.update(owner_id_filter())

    return all_filters


def _group_id_list_query_filter(group_id_list):
    _query_filter = {
        "OR": [
            {
                "group": {
                    "id": {"eq": group_id},
                }
            }
            for group_id in group_id_list
            if group_id is not None
        ],
    }
    if None in group_id_list:
        _query_filter["OR"].append(
            {
                "group": {
                    "hasSome": {"is": False},
                }
            },
        )

    return (_query_filter,)


def _group_name_list_query_filter(group_name_list):
    _query_filter = {
        "OR": [
            {
                "group": {
                    "name": string_exact_lc(group_name),
                }
            }
            for group_name in group_name_list
            if group_name != ""
        ],
    }
    if "" in group_name_list:
        _query_filter["OR"].append(
            {
                "group": {
                    "hasSome": {"is": False},
                }
            },
        )

    return (_query_filter,)


def query_filters(
    fqdn=None,
    display_name=None,
    hostname_or_id=None,
    insights_id=None,
    provider_id=None,
    provider_type=None,
    updated_start=None,
    updated_end=None,
    group_name=None,
    group_ids=None,
    tags=None,
    staleness=None,
    registered_with=None,
    filter=None,
    rbac_filter=None,
):
    num_ids = 0
    for id_param in [fqdn, display_name, hostname_or_id, insights_id]:
        if id_param:
            num_ids += 1

    if num_ids > 1:
        raise ValidationException(
            "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        )

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
        tag_filters = build_tag_query_dict_tuple(tags)
        query_filters += ({"OR": tag_filters},)
    if staleness:
        staleness_filters = tuple(staleness_filter(staleness))
        query_filters += ({"OR": staleness_filters},)

    if registered_with:
        query_filters += build_registered_with_filter(registered_with)
    if provider_type:
        query_filters += ({"provider_type": {"eq": provider_type.casefold()}},)
    if provider_id:
        query_filters += ({"provider_id": {"eq": provider_id.casefold()}},)
    if updated_start or updated_end:
        query_filters += _build_modified_on_filter(updated_start, updated_end)
    if group_name:
        query_filters += _group_name_list_query_filter(group_name)
    if group_ids:
        query_filters += _group_id_list_query_filter(group_ids)

    # If this feature flag is set, we should hide edge hosts by default, even if a filter wasn't provided.
    if get_flag_value(FLAG_HIDE_EDGE_HOSTS) and not filter:
        filter = {"system_profile": {"host_type": {"eq": "nil"}}}

    if filter:
        for key in filter:
            if key == "system_profile":
                # If a host_type filter wasn't provided in the request, filter out edge hosts.
                if get_flag_value(FLAG_HIDE_EDGE_HOSTS) and "host_type" not in filter["system_profile"]:
                    filter["system_profile"]["host_type"] = {"eq": "nil"}

                query_filters += build_system_profile_filter(filter["system_profile"])
            else:
                raise ValidationException("filter key is invalid")

    if rbac_filter:
        for key in rbac_filter:
            if key == "groups":
                query_filters += _group_id_list_query_filter(rbac_filter["groups"])

    current_identity = get_current_identity()
    if current_identity.identity_type == IdentityType.SYSTEM:
        query_filters += (owner_id_filter(),)

    logger.debug(query_filters)
    return query_filters


def build_system_profile_filter(system_profile):
    system_profile_filter = tuple()

    for field_name in system_profile:
        _check_field_in_spec(system_profile_spec(), field_name)

        field_input = system_profile[field_name]
        field_filter = system_profile_spec()[field_name]["filter"]
        field_format = system_profile_spec()[field_name]["format"]
        is_array = system_profile_spec()[field_name]["is_array"]

        logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

        builder_function = _get_builder_function(field_filter, field_format)

        if field_name in custom_filter_fields:
            system_profile_filter += builder_function(field_name, field_input, field_filter)
        else:
            field_value, operation = _get_field_value_and_operation(field_input, field_filter, field_format, is_array)
            system_profile_filter += _generic_filter_builder(
                builder_function, field_name, field_value, field_filter, operation
            )

    return system_profile_filter
