import json
import re
from urllib.parse import quote
from urllib.parse import unquote

from connexion.exceptions import BadRequestProblem
from connexion.uri_parsing import OpenAPIURIParser
from connexion.utils import coerce_type

_BOOL_STRINGS = {"true": True, "false": False}


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

            prev[k] = (
                _coerce_query_value(leaf_value)
                if k in ("nil", "not_nil")
                else (parsed if parsed is not None else leaf_value)
            )

        return (root_key, [root], True)
