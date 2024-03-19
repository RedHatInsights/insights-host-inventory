from sqlalchemy import text

from api.filtering.filtering_common import POSTGRES_COMPARATOR_LOOKUP
from api.filtering.filtering_common import POSTGRES_DEFAULT_COMPARATOR
from app import system_profile_spec
from app.exceptions import ValidationException
from app.logging import get_logger

logger = get_logger(__name__)


class OsComparison:
    def __init__(self, name, comparator, major, minor):
        self.name = name
        self.comparator = comparator
        self.major = major
        self.minor = minor


def _check_field_in_spec(spec, field_name):
    if field_name not in spec.keys():
        raise ValidationException(f"invalid filter field: {field_name}")


def _convert_dict_to_text_filter_and_value(filter: dict):
    key = next(iter(filter.keys()))
    val = filter[key]

    # If the next node is not the deepest value
    if type(val) is dict:
        # Skip comparison node if present (eq, lt, gte, etc)
        next_key = next(iter(val.keys()))
        if next_key in POSTGRES_COMPARATOR_LOOKUP.keys():
            return f"->>'{key}'", POSTGRES_COMPARATOR_LOOKUP.get(next_key), next(iter(val.values()))

        # Recurse
        next_val, pg_op, deepest_value = _convert_dict_to_text_filter_and_value(val)
        return f"->'{key}'{next_val}", pg_op, deepest_value
    else:
        # Get the final jsonb path node and its value; no comparator was specified
        return f"->>'{key}'", None, val


def _get_field_filter_for_deepest_param(sp_spec: dict, filter: dict):
    # Skip through "children" nodes in the spec
    if "children" in sp_spec:
        return _get_field_filter_for_deepest_param(sp_spec["children"], filter)

    key = next(iter(filter.keys()))
    val = filter[key]

    if type(val) is dict:
        if key in sp_spec:
            return _get_field_filter_for_deepest_param(sp_spec[key], filter[key])

    # If we find a comparator, we're already at the deepest node
    if key in POSTGRES_COMPARATOR_LOOKUP.keys():
        return sp_spec["filter"]

    return sp_spec[key]["filter"]


# Extracts specific filters from the filter param object and puts them in an easier format
# {'RHEL': {'version': {'lt': '9.0', 'gt': '8.5'}}} should become:
# [
#   OsComparison{name: 'RHEL', comparator: 'lt', major: '9', minor: '0'}
#   OsComparison{name: 'RHEL', comparator: 'gt', major: '8', minor: '5'}
# ]
def separate_operating_system_filters(filter_param: dict) -> list:
    os_filter_list = []
    for os_name in filter_param.keys():
        if not isinstance(version_node := filter_param[os_name]["version"], dict):
            # If there's no comparator, treat it as "eq"
            version = filter_param[os_name]["version"]
            version_split = version.split(".")
            os_filter_list.append(OsComparison(os_name, "eq", version_split[0], version_split[1]))
        else:
            for os_comparator in version_node.keys():
                version = filter_param[os_name]["version"][os_comparator]
                version_split = version.split(".")
                os_filter_list.append(OsComparison(os_name, os_comparator, version_split[0], version_split[1]))

    return os_filter_list


def build_operating_system_filter_list(filter_param):
    os_filter_list = []
    separated_filters = separate_operating_system_filters(filter_param["operating_system"])

    for os_comparison in separated_filters:
        comparator = POSTGRES_COMPARATOR_LOOKUP.get(os_comparison.comparator)
        comparator_no_eq = comparator[:1]

        if os_comparison.comparator == "eq":
            os_filter_text = (
                f"(system_profile_facts->'operating_system'->>'name' = '{os_comparison.name}' AND "
                f"(system_profile_facts->'operating_system'->>'major')::int = {os_comparison.major} AND "
                f"(system_profile_facts->'operating_system'->>'minor')::int = {os_comparison.minor})"
            )
        else:
            os_filter_text = (
                f"(system_profile_facts->'operating_system'->>'name' = '{os_comparison.name}' AND "
                f"((system_profile_facts->'operating_system'->>'major')::int {comparator_no_eq} {os_comparison.major}"
                f" OR ((system_profile_facts->'operating_system'->>'major')::int = {os_comparison.major} AND "
                f"(system_profile_facts->'operating_system'->>'minor')::int {comparator} {os_comparison.minor})))"
            )

        os_filter_list.append(os_filter_text)

    # If multiple OS filters are provided, it should be treated as "OR"
    return (text(" OR ".join(os_filter_list)),)


def _build_dict_from_path_list(path_list: list) -> dict:
    if len(path_list) > 1:
        return {path_list[0]: _build_dict_from_path_list(path_list[1:])}
    else:
        return path_list[0]


def _unique_paths(
    node,
    ignore_nodes=[],
    current_path=[],
):
    all_filters = []
    if isinstance(node, dict):
        # Not a leaf node
        for key in node.keys():
            if key in ignore_nodes:
                all_filters.append(node)
            else:
                all_filters += _unique_paths(node[key], ignore_nodes, [*current_path, key])
    else:
        # We've reached a leaf node
        if isinstance(node, list):
            for item in node:
                all_filters += [_build_dict_from_path_list([*current_path, item])]

        else:
            all_filters = [_build_dict_from_path_list([*current_path, node])]

    return all_filters


def build_system_profile_filter(system_profile_param):
    system_profile_filter = tuple()

    # Separate the filter object into a list of filters
    filter_param_list = _unique_paths(system_profile_param, ["operating_system"])

    for filter_param in filter_param_list:
        field_name = next(iter(filter_param.keys()))
        _check_field_in_spec(system_profile_spec(), field_name)

        if field_name == "operating_system":
            system_profile_filter += build_operating_system_filter_list(filter_param)
        else:
            # Main SP filters
            field_input = filter_param[field_name]
            field_filter = _get_field_filter_for_deepest_param(system_profile_spec(), filter_param)

            logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

            jsonb_path, pg_op, value = _convert_dict_to_text_filter_and_value(filter_param)

            if not pg_op:
                pg_op = POSTGRES_DEFAULT_COMPARATOR.get(field_filter)

            # Handle wildcard fields (use ILIKE, replace * with %)
            if pg_op == "ILIKE":
                value = value.replace("*", "%")

            # Put value in quotes if appropriate for the field type
            if field_filter in ["wildcard", "string", "timestamp", "boolean"]:
                value = f"'{value}'"

            text_filter = f"system_profile_facts{jsonb_path} {pg_op} {value}"

            system_profile_filter += (text(text_filter),)

    return system_profile_filter
