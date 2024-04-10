from sqlalchemy import text

from api.filtering.filtering_common import FIELD_FILTER_TO_POSTGRES_CAST
from api.filtering.filtering_common import POSTGRES_COMPARATOR_LOOKUP
from api.filtering.filtering_common import POSTGRES_DEFAULT_COMPARATOR
from app import system_profile_spec
from app.exceptions import ValidationException
from app.logging import get_logger

logger = get_logger(__name__)


# Utility class to facilitate OS filter comparison
class OsComparison:
    def __init__(self, name, comparator, major, minor):
        self.name = name
        self.comparator = comparator
        self.major = major
        self.minor = minor


def _check_field_in_spec(spec, field_name):
    if field_name not in spec.keys():
        raise ValidationException(f"invalid filter field: {field_name}")


# Takes a filter dict and converts it into:
#   jsonb_path: The jsonb path, i.e. system_profile_facts->sap->>sap_system
#   pg_op: The comparison to use (e.g. =, >, <)
#   value: The filter's value
def _convert_dict_to_text_filter_and_value(filter: dict, get_node_instead_of_value: bool = False) -> tuple:
    key = next(iter(filter.keys()))
    val = filter[key]

    # If the next node is not the deepest value
    if isinstance(val, dict):
        # Skip comparison node if present (eq, lt, gte, etc)
        next_key = next(iter(val.keys()))
        if next_key in POSTGRES_COMPARATOR_LOOKUP.keys():
            jsonb_operator = "->" if get_node_instead_of_value else "->>"
            return f"{jsonb_operator}'{key}'", POSTGRES_COMPARATOR_LOOKUP.get(next_key), next(iter(val.values()))

        # Recurse
        next_val, pg_op, deepest_value = _convert_dict_to_text_filter_and_value(val, get_node_instead_of_value)
        return f"->'{key}'{next_val}", pg_op, deepest_value
    else:
        # Get the final jsonb path node and its value; no comparator was specified
        jsonb_operator = "->" if get_node_instead_of_value else "->>"
        return f"{jsonb_operator}'{key}'", None, val


# Gets the deepest node in the "filter" object, and looks up its field_filter in sp_spec
def _get_field_filter_for_deepest_param(sp_spec: dict, filter: dict) -> str:
    # If the node is an array, that's as far as we go
    if sp_spec.get("is_array") is True:
        return "array"

    # Skip through "children" nodes in the spec
    if "children" in sp_spec:
        return _get_field_filter_for_deepest_param(sp_spec["children"], filter)

    key = next(iter(filter.keys()))

    # If the current key is a comparator, we're already at the deepest node
    if key in POSTGRES_COMPARATOR_LOOKUP.keys():
        return sp_spec["filter"]

    # Make sure the requested field is in the spec
    _check_field_in_spec(sp_spec, key)
    val = filter[key]

    if isinstance(val, dict):
        if key in sp_spec:
            return _get_field_filter_for_deepest_param(sp_spec[key], filter[key])

    # If the next node is an array, that's as far as we go
    if sp_spec[key].get("is_array") is True:
        return "array"

    return sp_spec[key]["filter"]


def _get_valid_os_names() -> list:
    return system_profile_spec()["operating_system"]["children"]["name"]["enum"]


# Extracts specific filters from the filter param object and puts them in an easier format
# For instance, {'RHEL': {'version': {'lt': '9.0', 'gt': '8.5'}}} becomes:
# [
#   OsComparison{name: 'RHEL', comparator: 'lt', major: '9', minor: '0'}
#   OsComparison{name: 'RHEL', comparator: 'gt', major: '8', minor: '5'}
# ]
# Has a similar purpose to _unique_paths, but the OS filter works a bit differently.
def separate_operating_system_filters(filter_param: dict) -> list[OsComparison]:
    os_filter_list = []
    for os_name in filter_param.keys():
        if os_name not in (os_names := _get_valid_os_names()):
            raise ValidationException(f"operating_system filter only supports these OS names: {os_names}.")

        if not isinstance(version_node := filter_param[os_name]["version"], dict):
            # If there's no comparator, treat it as "eq"
            version_node = {"eq": version_node}

        for os_comparator in version_node.keys():
            version_array = version_node[os_comparator]
            if not isinstance(version_array, list):
                version_array = [version_array]

            for version in version_array:
                version_split = version.split(".")
                if len(version_split) > 2:
                    raise ValidationException("operating_system filter can only have a major and minor version.")

                for v in version_split:
                    if not v.isdigit():
                        raise ValidationException("operating_system major and minor versions must be numerical.")

                if len(version_split) == 2:
                    os_filter_list.append(OsComparison(os_name, os_comparator, version_split[0], version_split[1]))
                else:
                    # If the minor version is not provided, then things get more complicated.
                    # Using version 8 as an example, here's how the logic should work:
                    # gte 8 -> gte 8.0
                    # gt  8 -> gte 9.0
                    # lte 8 -> lt  9.0
                    # lt  8 -> lt  8.0
                    # eq  8 -> gte 8.0 AND lt 9.0

                    if os_comparator == "eq":
                        os_filter_list.append(OsComparison(os_name, "gte", version_split[0], 0))
                        os_filter_list.append(OsComparison(os_name, "lt", str(int(version_split[0]) + 1), 0))
                    else:
                        new_major_version = version_split[0]
                        new_comparator = os_comparator
                        if os_comparator in ["gt", "lte"]:
                            new_major_version = str(int(new_major_version) + 1)
                        if os_comparator == "gt":
                            new_comparator = "gte"
                        elif os_comparator == "lte":
                            new_comparator = "lt"

                        os_filter_list.append(OsComparison(os_name, new_comparator, new_major_version, 0))

    return os_filter_list


# Takes an OS filter param and converts it into a tuple containing the DB filter
def build_operating_system_filter(filter_param: dict) -> tuple:
    os_filter_list = []  # Top-level filter
    os_range_filter_list = []  # Contains the OS filters that use range operations
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
            os_filter_list.append(os_filter_text)
        else:
            # Add to AND filter
            os_filter_text = (
                f"(system_profile_facts->'operating_system'->>'name' = '{os_comparison.name}' AND "
                f"((system_profile_facts->'operating_system'->>'major')::int {comparator_no_eq} {os_comparison.major}"
                f" OR ((system_profile_facts->'operating_system'->>'major')::int = {os_comparison.major} AND "
                f"(system_profile_facts->'operating_system'->>'minor')::int {comparator} {os_comparison.minor})))"
            )
            os_range_filter_list.append(os_filter_text)

    # If there's anything in the range operations filter list, AND them and add to the main list.
    if len(os_range_filter_list) > 0:
        os_filter_list.append(f"({' AND '.join(os_range_filter_list)})")

    # The top-level filter list should be joined using "OR"
    return " OR ".join(os_filter_list)


# Turns a list into a dict like this:
# [foo, bar, baz] -> {"foo": {"bar": "baz"}}
def _build_dict_from_path_list(path_list: list) -> dict:
    if len(path_list) > 1:
        return {path_list[0]: _build_dict_from_path_list(path_list[1:])}
    else:
        return path_list[0]


# Takes a deep object and reduces it into a list of unique paths.
# For instance, {"foo": {"bar": "val1", "baz": "val2"}} becomes:
# [{"foo": {"bar": "val1"}}, {"foo": {"baz": "val2"}}]
#
# When multiple values are provided for one filter, the paths are grouped in a list,
# making them easier to logically group.
# For instance, [{"foo": {"bar": "val1"}, "baz": ["val2", "val3"]}] becomes:
# [{"foo": {"bar": "val1"}}, [{"foo": {"baz": "val2"}}, {"foo": {"baz": "val3"}}]]
def _unique_paths(
    node: dict,
    ignore_nodes: list = [],
    current_path: list = [],
) -> list[dict]:
    all_filters = []
    if isinstance(node, dict):
        # Not a leaf node
        for key in node.keys():
            if key in ignore_nodes:
                # Skip recursion on ignored nodes.
                # Instead, just add the whole thing to the output.
                all_filters.append(node)
            else:
                all_filters += _unique_paths(node[key], ignore_nodes, [*current_path, key])
    else:
        # We've reached a leaf node
        if isinstance(node, list):
            # Adding a list of filters means we're going to OR these values together
            all_filters.append([_build_dict_from_path_list([*current_path, item]) for item in node])

        else:
            all_filters = [_build_dict_from_path_list([*current_path, node])]

    return all_filters


def escape_sql_from_string_val(val: str, pg_op: str) -> str:
    value = val
    if "%" in value and pg_op == "ILIKE":
        value = value.replace("%", r"\%")
    if "/" in value:
        value = value.replace("/", r"\/")
    if ":" in value:
        value = value.replace(":", r"\:")
    if "'" in value:
        value = value.replace("'", r"''")
    return value


def build_single_text_filter(filter_param: dict) -> str:
    field_name = next(iter(filter_param.keys()))

    if field_name == "operating_system":
        return build_operating_system_filter(filter_param)
    else:
        # Main SP filters
        field_input = filter_param[field_name]
        field_filter = _get_field_filter_for_deepest_param(system_profile_spec(), filter_param)

        logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

        jsonb_path, pg_op, value = _convert_dict_to_text_filter_and_value(filter_param, field_filter == "array")

        if not pg_op:
            pg_op = POSTGRES_DEFAULT_COMPARATOR.get(field_filter)

        value = escape_sql_from_string_val(value, pg_op)

        # Handle wildcard fields (use ILIKE, replace * with %)
        if pg_op == "ILIKE":
            value = value.replace("*", "%")

        if value == "nil":
            pg_op = "IS"
            value = "NULL"
        elif value == "not_nil":
            pg_op = "IS"
            value = "NOT NULL"

        # Put value in quotes if appropriate for the field type and operation
        if field_filter in ["wildcard", "string", "timestamp", "boolean", "array"] and pg_op != "IS":
            value = f"'{value}'"
        elif value == "" or (
            field_filter == "integer" and (not value.isdigit() and value not in ["NULL", "NOT NULL"])
        ):
            raise ValidationException(f"'{value}' is an invalid value for field {field_name}")

        pg_cast = FIELD_FILTER_TO_POSTGRES_CAST.get(field_filter, "")

        text_filter = f"(system_profile_facts{jsonb_path}){pg_cast} {pg_op} {value}"

        return text_filter


# Takes a System Profile filter param and turns it into sql filters.
def build_system_profile_filter(system_profile_param: dict) -> tuple:
    system_profile_filter = tuple()

    # Separate the filter object into a list of filters
    filter_param_list = _unique_paths(system_profile_param, ["operating_system"])

    for grouped_filter_param in filter_param_list:
        if isinstance(grouped_filter_param, list):
            # Usually, when multiple filters are grouped, join the list with "OR"
            conjunction = " OR "
            # When the filtered field is an array or OS, join the list with " AND "
            if _get_field_filter_for_deepest_param(system_profile_spec(), grouped_filter_param[0]) == "array":
                conjunction = " AND "

            filter_list = conjunction.join(
                [build_single_text_filter(single_filter) for single_filter in grouped_filter_param]
            )
            text_filter = f"({filter_list})"
        else:
            text_filter = build_single_text_filter(grouped_filter_param)

        system_profile_filter += (text(text_filter),)

    return system_profile_filter
