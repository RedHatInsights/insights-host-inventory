import json
import re
from urllib.parse import quote
from urllib.parse import unquote

from connexion.exceptions import BadRequestProblem
from connexion.uri_parsing import OpenAPIURIParser
from connexion.utils import coerce_type


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
    def _try_parse_json(value):
        """Try to parse a JSON string. Returns the parsed dict or None if not valid JSON object."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
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
            parsed = customURIParser._try_parse_json(v)
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
            parsed = customURIParser._try_parse_json(leaf_value)
            prev[k] = parsed if parsed is not None else leaf_value

        return (root_key, [root], True)
