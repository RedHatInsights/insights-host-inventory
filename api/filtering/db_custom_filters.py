from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.sql.expression import ColumnOperators

from api.filtering.filtering_common import FIELD_FILTER_TO_POSTGRES_CAST
from api.filtering.filtering_common import FIELD_FILTER_TO_PYTHON_CAST
from api.filtering.filtering_common import POSTGRES_COMPARATOR_LOOKUP
from api.filtering.filtering_common import POSTGRES_COMPARATOR_NO_EQ_LOOKUP
from api.filtering.filtering_common import POSTGRES_DEFAULT_COMPARATOR
from api.filtering.filtering_common import get_valid_os_names
from app import system_profile_spec
from app.config import HOST_TYPES
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models import Host

logger = get_logger(__name__)


# Utility class to facilitate OS filter comparison
# The list of comparators can be seen in POSTGRES_COMPARATOR_LOOKUP
class OsFilter:
    def __init__(self, name="", comparator="", version=None):
        try:
            if version is None:
                major, minor = None, None
            else:
                version_split = version.split(".")

                if len(version_split) > 2:
                    raise ValidationException("operating_system filter can only have a major and minor version.")
                elif len(version_split) == 1:  # only major version was sent
                    major = version_split[0]
                    minor = None
                else:
                    major, minor = version_split

                if not major.isdigit() or (minor and not minor.isdigit()):
                    raise ValidationException("operating_system major and minor versions must be numerical.")
        except ValidationException:
            raise

        self.name = name
        self.comparator = comparator
        self.major = major
        self.minor = minor


def _check_field_in_spec(spec: dict, field_name: str, parent_node: str) -> None:
    if field_name not in spec.keys():
        raise ValidationException(f"Invalid operation or child node for {parent_node}: {field_name}")


# Takes a filter dict and converts it into:
#   jsonb_path: The jsonb path, i.e. (system_profile_facts, sap, sap_system,)
#   pg_op: The comparison to use (e.g. =, >, <)
#   value: The filter's value
def _convert_dict_to_json_path_and_value(
    filter: dict,
) -> tuple[tuple[str], str | None, str]:  # Tuple of keys for the json path; pg_op; leaf node
    key: str = next(iter(filter.keys()))
    val = filter[key]

    # If the next node is not the deepest value
    if isinstance(val, dict):
        # Skip comparison node if present (eq, lt, gte, etc)
        next_key = next(iter(val.keys()))
        if op := POSTGRES_COMPARATOR_LOOKUP.get(next_key):
            return (key,), op, next(iter(val.values()))

        # Recurse
        next_val, pg_op, deepest_value = _convert_dict_to_json_path_and_value(val)
        return (key, *next_val), pg_op, deepest_value  # type: ignore [return-value]
    else:
        # Get the final jsonb path node and its value; no comparator was specified
        return (key,), None, val


# Gets the deepest node in the "filter" object, and looks up its field_filter in sp_spec
def _get_field_filter_for_deepest_param(sp_spec: dict, filter: dict, parent_node: str = "system_profile") -> str:
    # If the node is an array, that's as far as we go
    if sp_spec.get("is_array") is True:
        return "array"

    # Skip through "children" nodes in the spec
    if "children" in sp_spec:
        return _get_field_filter_for_deepest_param(sp_spec["children"], filter, parent_node)

    key = next(iter(filter.keys()))

    # If the current key is a comparator, we're already at the deepest node
    if key in POSTGRES_COMPARATOR_LOOKUP.keys():
        if "filter" in sp_spec.keys():
            return sp_spec["filter"]
        elif sp_spec:
            return "object"

    # Make sure the requested field is in the spec
    _check_field_in_spec(sp_spec, key, parent_node)
    val = filter[key]

    if isinstance(val, dict) and key in sp_spec:
        return _get_field_filter_for_deepest_param(sp_spec[key], filter[key], key)

    # If the next node is an array, that's as far as we go
    if sp_spec[key].get("is_array") is True:
        return "array"

    return sp_spec[key]["filter"]


# Extracts specific filters from the filter param object and puts them in an easier format
# For instance, {'RHEL': {'version': {'lt': '9.0', 'gt': '8.5'}}} becomes:
# [
#   OsFilter{name: 'RHEL', major: '9', minor: '0', comparator: 'lt'}
#   OsFilter{name: 'RHEL', major: '8', minor: '5', comparator: 'gt'}
# ]
# Has a similar purpose to _unique_paths, but the OS filter works a bit differently.
def separate_operating_system_filters(filter_url_params) -> list[OsFilter]:
    os_filter_list: list[OsFilter] = []

    # Handle filter_url_params if a list is passed in
    if isinstance(filter_url_params, list):
        return [OsFilter(comparator=param) for param in filter_url_params]

    # Handle filter_url_params if a str is passed in
    elif isinstance(filter_url_params, str):
        return [OsFilter(comparator=filter_url_params)]

    # filter_url_params is a dict
    for filter_key in filter_url_params.keys():
        if filter_key == "name":
            ((os_comparator, os_name),) = filter_url_params[filter_key].items()
            version_node = {os_comparator: [None]}
        else:
            os_name = filter_key
            if not isinstance(version_node := filter_url_params[os_name].get("version"), dict):
                # If there's no comparator, treat it as "eq"
                version_node = {"eq": version_node}

        if not isinstance(os_name, list):
            os_name = [os_name]
        for name in os_name:
            os_filter_list += create_os_filter(name, version_node)

    return os_filter_list


# Takes an OS filter param and converts it into a tuple containing the DB filter
def build_operating_system_filter(filter_param: dict) -> tuple:
    os_filter_list = []  # Top-level filter
    os_range_filter_list = []  # Contains the OS filters that use range operations
    os_field = Host.system_profile_facts["operating_system"]

    separated_filters = separate_operating_system_filters(filter_param["operating_system"])

    for os_filter in separated_filters:
        comparator = POSTGRES_COMPARATOR_LOOKUP.get(os_filter.comparator)

        if os_filter.comparator in ["nil", "not_nil"]:
            # Uses the comparator with None, resulting in either is_(None) or is_not(None)
            os_filter_list.append(os_field.astext.operate(comparator, None))

        elif os_filter.comparator in ["eq", "neq"]:
            os_filters = [
                func.lower(os_field["name"].astext).operate(comparator, os_filter.name.lower()),
            ]

            if os_filter.major is not None:
                os_filters.append(os_field["major"].astext.cast(Integer) == os_filter.major)

            if os_filter.minor:
                os_filters.append(os_field["minor"].astext.cast(Integer) == os_filter.minor)

            os_filter_list.append(and_(*os_filters))
        else:
            if os_filter.minor is not None:
                # If the minor version is specified, the os_filter logic is a bit more complex. For instance:
                # input: version <= 9.5
                # output: (major < 9) OR (major = 9 AND minor <= 5)
                comparator_no_eq = POSTGRES_COMPARATOR_NO_EQ_LOOKUP.get(os_filter.comparator)
                os_filter = and_(
                    os_field["name"].astext == os_filter.name,
                    or_(
                        os_field["major"].astext.cast(Integer).operate(comparator_no_eq, os_filter.major),
                        and_(
                            os_field["major"].astext.cast(Integer) == os_filter.major,
                            os_field["minor"].astext.cast(Integer).operate(comparator, os_filter.minor),
                        ),
                    ),
                )

            else:
                os_filter = and_(
                    os_field["name"].astext == os_filter.name,
                    os_field["major"].astext.cast(Integer).operate(comparator, os_filter.major),
                )

            # Add to AND filter
            os_range_filter_list.append(os_filter)

    # If there's anything in the range operations filter list, AND them and add to the main list.
    if len(os_range_filter_list) > 0:
        os_filter_list.append(and_(*os_range_filter_list))
    # The top-level filter list should be joined using "OR"
    return or_(*os_filter_list)


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
    ignore_nodes: list | None = None,
    current_path: list | None = None,
) -> list[dict]:
    if ignore_nodes is None:
        ignore_nodes = []
    if current_path is None:
        current_path = []
    all_filters = []

    if isinstance(node, dict):
        # Not a leaf node
        for key in node.keys():
            if key in ignore_nodes:
                # Skip recursion on ignored nodes.
                # Instead, just add the whole thing to the output.
                all_filters.append({key: node[key]})
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


def _validate_pg_op_and_value(pg_op: str | None, value: str, field_filter: str, field_name: str) -> None:
    if field_filter != "array" and pg_op == "contains":
        raise ValidationException(f"'contains' is an invalid operation for non-array field {field_name}")

    if (field_filter == "integer" and (not value.isdigit() and value not in ["nil", "not_nil"])) or (
        field_filter == "boolean" and value.lower() not in ["true", "false", "nil", "not_nil"]
    ):
        raise ValidationException(f"'{value}' is an invalid value for field {field_name}")


def build_single_filter(filter_param: dict) -> ColumnElement:
    field_name = next(iter(filter_param.keys()))

    if field_name == "operating_system":
        return build_operating_system_filter(filter_param)
    else:
        # Main SP filters
        field_input = filter_param[field_name]
        field_filter = _get_field_filter_for_deepest_param(system_profile_spec(), filter_param)

        logger.debug(f"generating filter: field: {field_name}, type: {field_filter}, field_input: {field_input}")

        value: str | None
        jsonb_path, pg_op, value = _convert_dict_to_json_path_and_value(filter_param)
        target_field = Host.system_profile_facts[(jsonb_path)].astext
        _validate_pg_op_and_value(pg_op, value, field_filter, field_name)

        # Use the default comparator for the field type, if not provided
        if not pg_op or not value:
            pg_op = POSTGRES_DEFAULT_COMPARATOR.get(field_filter)

        # Handle wildcard fields (use ILIKE, replace * with %)
        if pg_op == ColumnOperators.ilike:
            value = value.replace("*", "%")

        if value in ["nil", "not_nil"]:
            pg_op = POSTGRES_COMPARATOR_LOOKUP[value]
            value = None
        elif pg_cast := FIELD_FILTER_TO_POSTGRES_CAST.get(field_filter):
            # Cast column and value, if using an applicable type
            target_field = target_field.cast(pg_cast)
            value = FIELD_FILTER_TO_PYTHON_CAST[field_filter](value)

        # "contains" is not a column operator, so we have to do it manually
        if pg_op == "contains":
            return target_field.contains(value)

        return target_field.operate(pg_op, value)


# Standardize host_type SP filter and get its value(s)
def get_host_types_from_filter(host_type_filter: dict) -> set[str | None]:
    if host_type_filter:
        host_types = set()

        # Standardize the input in dict format
        if not isinstance(host_type_filter, dict):
            host_type_filter = {"eq": host_type_filter}
        for key in host_type_filter.keys():
            if key in POSTGRES_COMPARATOR_LOOKUP.keys():
                comparator = key
                value = host_type_filter[key]
            else:
                comparator = "eq"
                value = key

            # Convert single values to list format
            if not isinstance(value, list):
                value = [value]

            for val in value:
                if val == "not_nil":
                    val = HOST_TYPES[0]
                elif val == "nil" or val == "":
                    val = HOST_TYPES[1]

                if comparator == "eq":
                    host_types.add(val)
                elif comparator == "neq":
                    tmp_host_types = HOST_TYPES.copy()
                    tmp_host_types.remove(val)
                    host_types.update(tmp_host_types)

    else:
        host_types = set(HOST_TYPES.copy())

    return host_types


# Takes a System Profile filter param and turns it into sql filters.
def build_system_profile_filter(system_profile_param: dict) -> tuple:
    system_profile_filter: tuple = tuple()

    # Separate the filter object into a list of filters
    filter_param_list = _unique_paths(system_profile_param, ["operating_system"])

    for grouped_filter_param in filter_param_list:
        if isinstance(grouped_filter_param, list):
            # Use AND when filtering on an array, but otherwise use OR.
            conjunction = (
                and_
                if _get_field_filter_for_deepest_param(system_profile_spec(), grouped_filter_param[0]) == "array"
                else or_
            )
            filter = conjunction(build_single_filter(single_filter) for single_filter in grouped_filter_param)
        else:
            filter = build_single_filter(grouped_filter_param)

        system_profile_filter += (filter,)
    return system_profile_filter


def check_valid_os_name(name):
    os_names = get_valid_os_names()
    if name.lower() not in [name.lower() for name in os_names]:
        raise ValidationException(f"operating_system filter only supports these OS names: {os_names}.")


def get_major_minor_from_version(version_split: list[str]):
    if len(version_split) > 2:
        raise ValidationException("operating_system filter can only have a major and minor version.")

    if not [v.isdigit() for v in version_split]:
        raise ValidationException("operating_system major and minor versions must be numerical.")

    major = version_split.pop(0)
    minor = version_split[0] if version_split else None

    return major, minor


def create_os_filter(os_name, version_node):
    os_filter_list: list[OsFilter] = []
    check_valid_os_name(os_name)

    for os_comparator in version_node.keys():
        version_array = version_node[os_comparator]
        if not isinstance(version_array, list):
            version_array = [version_array]

        for version in version_array:
            os_filter_list.append(OsFilter(os_name, os_comparator, version))

    return os_filter_list
