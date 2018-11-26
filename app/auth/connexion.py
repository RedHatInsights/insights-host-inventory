from connexion.utils import get_function_from_name


__all__ = ["get_authenticated_views"]


def _is_requires_identity_param(param):
    """
    Determines whether the parameter means that the identity header is required.
    """
    return (
        param["in"] == "header"
        and param["name"] == "x-rh-identity"
        and param.get("required", False)
    )  # For header fields, "required" is optional and its default is false.


def _requires_identity(item):
    """
    Finds out whether the identity header is required by the item’s parameters.
    """
    params = item.get("parameters", [])
    return any(map(_is_requires_identity_param, params))


def _methods(path):
    """
    List all method action specifications from a path specification.
    """
    for key, value in path.items():
        if key == "parameters":
            continue
        yield value


def get_authenticated_views(api_spec):
    """
    Go through the API specification and get every view function with an information
    whether it requires the identity header.
    """
    paths = api_spec.get("paths", {})
    for path in paths.values():
        if not _requires_identity(path):
            continue

        for method in _methods(path):
            yield get_function_from_name(method["operationId"])
