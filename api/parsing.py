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
    def _preserve_url_encoded_asterisks(value):
        """
        Preserve URL-encoded asterisks by replacing them with a placeholder before URL decoding.

        This prevents URL-encoded %2A from being treated as wildcards in fields that support
        wildcard filtering. The placeholder will be restored to literal '*' characters later.

        Args:
            value: The URL parameter value that may contain %2A

        Returns:
            tuple: (processed_value, has_encoded_asterisks)
                - processed_value: Value with %2A replaced by placeholder
                - has_encoded_asterisks: Boolean indicating if %2A was found
        """
        if not isinstance(value, str):
            return value, False

        # Use a placeholder that's unlikely to appear in real data
        placeholder = "__URL_ENCODED_ASTERISK__"

        # Check if the value contains URL-encoded asterisks
        has_encoded_asterisks = "%2A" in value or "%2a" in value

        if has_encoded_asterisks:
            # Replace both uppercase and lowercase variants
            processed_value = value.replace("%2A", placeholder).replace("%2a", placeholder)
            return processed_value, True

        return value, False

    @staticmethod
    def _restore_url_encoded_asterisks(value, had_encoded_asterisks):
        """
        Restore URL-encoded asterisks from placeholder back to literal '*' characters.

        Args:
            value: The value that may contain placeholders
            had_encoded_asterisks: Boolean indicating if placeholders should be restored

        Returns:
            The value with placeholders restored to literal '*' characters
        """
        if not isinstance(value, str) or not had_encoded_asterisks:
            return value

        placeholder = "__URL_ENCODED_ASTERISK__"
        return value.replace(placeholder, "*")

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
            # Handle URL-encoded asterisks for array values
            processed_values = []
            encoded_asterisks_info = []

            for val in v:
                processed_val, had_encoded = customURIParser._preserve_url_encoded_asterisks(val)
                processed_values.append(unquote(processed_val))
                encoded_asterisks_info.append(had_encoded)

            # Restore literal asterisks for values that were URL-encoded
            final_values = []
            for val, had_encoded in zip(processed_values, encoded_asterisks_info, strict=True):
                final_val = customURIParser._restore_url_encoded_asterisks(val, had_encoded)
                final_values.append(final_val)

            prev[prev_k] = final_values
        else:
            if len(v) > 1:
                raise BadRequestProblem(f"Param {root_key} must be appended with [] to accept multiple values.")
            # Try to parse the value as JSON object
            leaf_value = v[0]

            # Handle URL-encoded asterisks for single values
            processed_leaf, had_encoded = customURIParser._preserve_url_encoded_asterisks(leaf_value)

            # Use the full parameter path for the error message (e.g., "filter[system_profile]")
            full_param_path = f"{root_key}[{']['.join(key_path)}]"
            parsed = customURIParser._try_parse_json(processed_leaf, param_name=full_param_path)

            # For filter params with only one path element (e.g., filter[system_profile]=value),
            # the value must be a JSON object. A plain string value at this level is invalid
            # because it would set the entire system_profile to a string instead of a nested filter.
            if parsed is None and len(key_path) == 1 and root_key == "filter":
                raise BadRequestProblem(
                    f"Filter param '{full_param_path}' value must be a JSON object or use bracket "
                    f"notation for nested fields (e.g., {full_param_path}[field]=value)."
                )

            if parsed is not None:
                final_value = parsed
            else:
                # URL decode the value
                decoded_value = unquote(processed_leaf)
                # Restore literal asterisks if they were originally URL-encoded
                final_value = customURIParser._restore_url_encoded_asterisks(decoded_value, had_encoded)

                # Apply coercion for special values
                if k in ("nil", "not_nil"):
                    final_value = _coerce_query_value(final_value)

            prev[k] = final_value

        return (root_key, [root], True)
