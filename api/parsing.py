import re

from connexion.decorators.uri_parsing import OpenAPIURIParser

from app.exceptions import ValidationException


def custom_fields_parser(root_key, key_path, val):
    """consumes values like ("a",["foo"],["baz,hello","world"])
    returns (a, {"foo": {"baz": True, "hello": True, "world": True}}}, is_deep_object)
    """
    root = {key_path[0]: {}}
    for v in val:
        for fields in v.split(","):
            root[key_path[0]][fields] = True
    return (root_key, [root], True)


class customURIParser(OpenAPIURIParser):
    @staticmethod
    def _make_deep_object(k, v):
        """consumes keys, value pairs like (a[foo][bar], "baz")
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
            if len(v) > 1:
                raise ValidationException(f"Param {root_key} must be appended with [] to accept multiple values.")
            prev[k] = v[0]
        return (root_key, [root], True)
