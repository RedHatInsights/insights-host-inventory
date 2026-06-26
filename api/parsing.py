import json
import re
from urllib.parse import quote
from urllib.parse import unquote

from connexion.exceptions import BadRequestProblem
from connexion.uri_parsing import OpenAPIURIParser
from connexion.utils import coerce_type
from flask import request

_BOOL_STRINGS = {"true": True, "false": False}


def _normalize_workspace_filters(
    group_name: str | list[str] | None,
    workspace_name: str | list[str] | None,
    group_id: str | list[str] | None,
    workspace_id: str | list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """
    Backwards compatibility: support both workspace_name/group_name and workspace_id/group_id filters.
        - If both group_name and workspace_name we abort with 400 error since they are mutually exclusive
        - If both group_id and workspace_id we abort with 400 error since they are mutually exclusive
        - Validate that the resulting workspace_name and workspace_id filters are not used simultaneously

        This allows clients to use either the old "group" parameters or the new "workspace" parameters
        and still supports breaking existing integrations,
        while ensuring that they don't mix filtering strategies in a single request.

    Args:
        workspace_name: Workspace name filter value (optional)
        workspace_id: Workspace ID filter value (optional)

    Raises:
        flask.abort(400): If both filters are provided simultaneously or if group and workspace filters are mixed
    """
    if workspace_name and group_name:
        raise BadRequestProblem("Cannot use both 'group_name' and 'workspace_name' filters together.")
    if workspace_id and group_id:
        raise BadRequestProblem("Cannot use both 'group_id' and 'workspace_id' filters together.")

    workspace_name = workspace_name or group_name
    workspace_id = workspace_id or group_id

    if workspace_name and workspace_id:
        raise BadRequestProblem(
            "Cannot use both 'workspace_name'/'group_name' and 'workspace_id'/'group_id' filters together. "
            "Please use only one workspace filter parameter.",
        )

    workspace_name = [workspace_name] if isinstance(workspace_name, str) else workspace_name
    workspace_id = [workspace_id] if isinstance(workspace_id, str) else workspace_id

    return workspace_name, workspace_id


def _coerce_query_value(value):
    """Coerce string query parameter values to native Python types.

    Query parameters are always strings, but deep object schemas may
    expect booleans.  Convert "true"/"false" so that jsonschema
    validation against ``type: boolean`` properties succeeds.
    """
    return _BOOL_STRINGS.get(value.lower(), value) if isinstance(value, str) else value


def custom_fields_parser(root_key, key_path, val):
    """
    Parse fields[app]=field1,field2 into {app: {field1: True, field2: True}}.

    Also accepts JSON array syntax: fields[app]=["field1","field2"].

    Examples:
        fields[advisor]=recommendations,incidents
            → {"advisor": {"recommendations": True, "incidents": True}}
        fields[system_profile]=arch,os_kernel_version
            → {"system_profile": {"arch": True, "os_kernel_version": True}}
        fields[system_profile]=["arch","os_kernel_version"]
            → {"system_profile": {"arch": True, "os_kernel_version": True}}
    """
    root = {key_path[0]: {}}
    for v in val:
        v = v.strip()
        fields_iterable = None

        if v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    fields_iterable = parsed
            except ValueError:
                pass

        if fields_iterable is None:
            fields_iterable = (field.strip() for field in v.split(","))

        for field in fields_iterable:
            if not isinstance(field, str):
                field = str(field)
            field = field.strip()
            if field:
                root[key_path[0]][field] = True
    return (root_key, [root], True)


class customURIParser(OpenAPIURIParser):
    # Override resolve_params to allow reserved characters in query params
    def resolve_params(self, params, _in):
        """
        takes a dict of parameters, and resolves the values into
        the correct array type handling duplicate values, and splitting
        based on the collectionFormat defined in the spec.
        """
        resolved_param = {}
        for k, values in params.items():
            param_defn = self.param_defns.get(k)
            param_schema = self.param_schemas.get(k)

            if not (param_defn or param_schema):
                # rely on validation
                resolved_param[k] = values
                continue

            if _in == "path":
                # multiple values in a path is impossible
                values = [values]

            if param_schema and param_schema["type"] == "array":
                # resolve variable re-assignment, handle explode
                if _in == "query":
                    values = [quote(value) for value in values]
                values = self._resolve_param_duplicates(values, param_defn, _in)
                # handle array styles
                if _in == "query":
                    resolved_param[k] = [unquote(value) for value in self._split(values, param_defn, _in)]
                else:
                    resolved_param[k] = self._split(values, param_defn, _in)
            else:
                resolved_param[k] = values[-1]

            # Skip coercion for 'fields' parameter - it uses a custom format that
            # doesn't match the OpenAPI schema structure (custom_fields_parser transforms
            # it into a dict format for internal use)
            if k != "fields":
                resolved_param[k] = coerce_type(param_defn, resolved_param[k], "parameter", k)

        return resolved_param

    @staticmethod
    def _preserve_encoded_wildcards_from_query(value, param_path, key_path):
        """
        Check the raw query string to determine if asterisks were URL-encoded.
        If they were, mark them as literal asterisks using a special marker.
        Only applies to fields that support wildcards.
        """
        if not isinstance(value, str):
            return value

        # Only apply this logic to wildcard fields
        if not customURIParser._is_wildcard_field(key_path):
            return value

        # Get the raw query string from the Flask request
        try:
            raw_query = request.query_string.decode("utf-8")

            # Look for this specific parameter in the raw query string
            # The param_path is already in the correct format (e.g., filter[system_profile][insights_client_version])

            # Check if the parameter was URL-encoded with %2A
            if f"{param_path}=" in raw_query:
                # Find the value part after the parameter
                param_start = raw_query.find(f"{param_path}=")
                if param_start != -1:
                    value_start = param_start + len(f"{param_path}=")
                    # Find the end of the value (next & or end of string)
                    value_end = raw_query.find("&", value_start)
                    if value_end == -1:
                        value_end = len(raw_query)

                    raw_value = raw_query[value_start:value_end]

                    # If the raw value contains %2A or %5C%2A, selectively mark encoded asterisks as literal
                    if "%2A" in raw_value or "%2a" in raw_value or "%5C%2A" in raw_value or "%5c%2a" in raw_value:
                        # Process the raw value to identify which asterisks were URL-encoded
                        marked_value = customURIParser._mark_encoded_asterisks_as_literal(raw_value, value)
                        return marked_value

        except Exception:
            # Fall back to original value if we can't check the raw query
            pass
        return value

    @staticmethod
    def _mark_encoded_asterisks_as_literal(raw_value, decoded_value):
        """
        Mark only the asterisks that were URL-encoded (%2A) as literal by adding backslashes.
        Leave unencoded asterisks as wildcards.
        """
        # Create a mapping of positions where %2A appears in the raw value
        # to positions where * appears in the decoded value
        result = list(decoded_value)
        raw_pos = 0
        decoded_pos = 0

        while raw_pos < len(raw_value) and decoded_pos < len(decoded_value):
            if raw_value[raw_pos : raw_pos + 3] in ("%2A", "%2a"):
                # Found URL-encoded asterisk, mark the corresponding decoded asterisk as literal
                if decoded_pos < len(result) and result[decoded_pos] == "*":
                    result[decoded_pos] = "\\*"
                raw_pos += 3  # Skip %2A
                decoded_pos += 1
            elif raw_value[raw_pos : raw_pos + 6] in ("%5C%2A", "%5c%2a"):
                # Found URL-encoded backslash + asterisk, already literal in decoded value
                raw_pos += 6  # Skip %5C%2A
                decoded_pos += 2  # Skip \*
            elif raw_value[raw_pos] == decoded_value[decoded_pos]:
                # Characters match, advance both
                raw_pos += 1
                decoded_pos += 1
            else:
                # Handle other URL-encoded characters
                if raw_value[raw_pos] == "%" and raw_pos + 2 < len(raw_value):
                    raw_pos += 3  # Skip URL-encoded character
                else:
                    raw_pos += 1
                decoded_pos += 1

        return "".join(result)

    @staticmethod
    def _is_wildcard_field(key_path):
        """
        Check if the field specified by key_path supports wildcards.
        key_path is a list like ['system_profile', 'insights_client_version']
        """
        try:
            from api.filtering.db_custom_filters import _get_field_filter_for_deepest_param
            from app import system_profile_spec

            # Build a filter dict to check the field type
            if len(key_path) < 2:
                return False

            # For system_profile filters, build the nested dict
            if key_path[0] == "system_profile" and len(key_path) >= 2:
                # Build the inner dict (without the 'system_profile' key)
                inner_dict = {}
                current = inner_dict
                for i in range(1, len(key_path) - 1):
                    current[key_path[i]] = {}
                    current = current[key_path[i]]
                current[key_path[-1]] = "dummy_value"

                # Check if this field has wildcard filter type
                field_filter = _get_field_filter_for_deepest_param(system_profile_spec(), inner_dict)
                return field_filter == "wildcard"

            return False
        except Exception:
            # If we can't determine the field type, don't apply wildcard processing
            return False

    @staticmethod
    def _try_parse_json(value, param_name=None):
        """
        Try to parse a JSON object string.

        Only attempts parsing if the value looks like it could be JSON (starts with '{' or '[').
        This prevents plain string values like "true", "false", or "15.3" from being
        interpreted as JSON primitives.

        Returns:
            - The parsed dict if value is a valid JSON object
            - None if value doesn't look like JSON, is invalid JSON, or is already a dict

        Raises:
            BadRequestProblem if value is a valid JSON array (arrays are not supported as
            filter values - use bracket notation like filter[field][]=value1&filter[field][]=value2).
        """
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            # Only attempt JSON parsing if it looks like a JSON object or array
            if stripped.startswith("{"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        return parsed
                    # Parsed successfully but not a dict (shouldn't happen for '{' prefix)
                    raise BadRequestProblem(f"Filter param '{param_name or 'filter'}' must be a JSON object.")
                except (json.JSONDecodeError, ValueError):
                    # Not valid JSON - treat as regular string value
                    # (e.g., os_release values like "{major}.{minor}" are not JSON)
                    pass
            elif stripped.startswith("["):
                # Check if it's actually a valid JSON array - only then reject it
                # Strings that merely start with '[' but aren't valid JSON are treated as regular values
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        raise BadRequestProblem(
                            f"Filter param '{param_name or 'filter'}' must be a JSON object, not an array."
                        )
                except (json.JSONDecodeError, ValueError):
                    # Not valid JSON - treat as regular string value
                    pass
        return None

    @staticmethod
    def _make_deep_object(k, v):
        """consumes keys, value pairs like (a[foo][bar], "baz")
        returns (a, {"foo": {"bar": "baz"}}}, is_deep_object)

        Also supports JSON object notation:
        - (filter, '{"system_profile": {"arch": "x86_64"}}') -> (filter, [{"system_profile": ...}], True)
        - (filter[system_profile], ['{"arch": "x86_64"}']) -> (filter, [{"system_profile": {"arch": ...}}], True)
        """
        root_key = k.split("[", 1)[0]
        if k == root_key:
            # No square brackets in key
            # If v is already a dict or a JSON string, treat as deep object and pass through
            parsed = customURIParser._try_parse_json(v, param_name=k)
            if parsed is not None:
                return (root_key, [parsed], True)
            return (k, v, False)

        key_path = re.findall(r"\[([^\[\]]*)\]", k)
        root = prev = node = {}

        if root_key == "fields":
            return custom_fields_parser(root_key, key_path, v)

        prev_k = root_key
        for k in key_path:
            if k != "":  # skip [] to avoid creating dict with empty string as key
                node[k] = {}
                prev = node
                node = node[k]
                prev_k = k
        # if the final value of k is '' it corresponds to a path ending with []
        # this indicates an array parameter.
        # in this case we want to add all the values, not just the 0th
        if k == "":
            prev[prev_k] = v
        else:
            if len(v) > 1:
                raise BadRequestProblem(f"Param {root_key} must be appended with [] to accept multiple values.")
            # Try to parse the value as JSON object
            leaf_value = v[0]
            # Use the full parameter path for the error message (e.g., "filter[system_profile]")
            full_param_path = f"{root_key}[{']['.join(key_path)}]"
            parsed = customURIParser._try_parse_json(leaf_value, param_name=full_param_path)

            # For filter params with only one path element (e.g., filter[system_profile]=value),
            # the value must be a JSON object. A plain string value at this level is invalid
            # because it would set the entire system_profile to a string instead of a nested filter.
            if parsed is None and len(key_path) == 1 and root_key == "filter":
                raise BadRequestProblem(
                    f"Filter param '{full_param_path}' value must be a JSON object or use bracket "
                    f"notation for nested fields (e.g., {full_param_path}[field]=value)."
                )

            # For filter parameters, preserve URL-encoded asterisks and backslashes
            # to distinguish literal from wildcard characters (only for wildcard fields)
            if root_key == "filter" and parsed is None:
                leaf_value = customURIParser._preserve_encoded_wildcards_from_query(
                    leaf_value, full_param_path, key_path
                )

            prev[k] = (
                _coerce_query_value(leaf_value)
                if k in ("nil", "not_nil")
                else (parsed if parsed is not None else leaf_value)
            )

        return (root_key, [root], True)
