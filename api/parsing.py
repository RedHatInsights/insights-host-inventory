import re

from connexion.decorators.uri_parsing import OpenAPIURIParser

from api.fields_parser import custom_fields_parser


class customURIParser(OpenAPIURIParser):
    @staticmethod
    def _make_deep_object(k, v):
        """ consumes keys, value pairs like (a[foo][bar], "baz")
            returns (a, {"foo": {"bar": "baz"}}}, is_deep_object)
        """

        root_key = k.split("[", 1)[0]
        if k == root_key:
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
            prev[k] = v[0]
        return (root_key, [root], True)
