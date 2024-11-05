import hbi_api_core


def get_assignment_rules(params=None, headers=None):
    if params is None:
        params = {}
    if headers is None:
        headers = {}

    resp = hbi_api_core.hbi_get("assignment-rules", additional_headers=headers, params=params)

    return resp


def get_hosts(params=None, headers=None):
    if params is None:
        params = {}
    if headers is None:
        headers = {}

    resp = hbi_api_core.hbi_get("hosts", additional_headers=headers, params=params)

    return resp


def get_marketplace_hosts(params=None, headers=None):
    if params is None:
        params = {}
    if headers is None:
        headers = {}

    return get_hosts(params={"filter[system_profile][is_marketplace]": "not_nil"})
