from __future__ import annotations

import json
import math
from base64 import b64encode
from collections.abc import Callable
from datetime import timedelta
from enum import Enum
from http import HTTPStatus
from itertools import product
from struct import unpack
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import quote_plus as url_quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from uuid import UUID

import dateutil.parser
from requests import Request
from requests import Response
from requests.structures import CaseInsensitiveDict

from app.auth.identity import IdentityType
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Host
from app.utils import HostWrapper
from tests.helpers.test_utils import now

BASE_URL = "/api/inventory/v1"
LEGACY_BASE_URL = "/r/insights/platform/inventory/v1"
HOST_URL = f"{BASE_URL}/hosts"
HOST_EXISTS_URL = f"{BASE_URL}/host_exists"
LEGACY_HOST_URL = f"{LEGACY_BASE_URL}/hosts"
GROUP_URL = f"{BASE_URL}/groups"
TAGS_URL = f"{BASE_URL}/tags"
SYSTEM_PROFILE_URL = f"{BASE_URL}/system_profile"
RESOURCE_TYPES_URL = f"{BASE_URL}/resource-types"
STALENESS_URL = f"{BASE_URL}/account/staleness"

SHARED_SECRET = "SuperSecretStuff"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = [
    [
        {"namespace": "NS1", "key": "key1", "value": "val1"},
        {"namespace": "NS1", "key": "key2", "value": "val1"},
        {"namespace": "SPECIAL", "key": "tag", "value": "ToFind"},
        {"namespace": "no", "key": "key", "value": None},
    ],
    [
        {"namespace": "NS1", "key": "key1", "value": "val1"},
        {"namespace": "NS2", "key": "key2", "value": "val2"},
        {"namespace": "NS3", "key": "key3", "value": "val3"},
    ],
    [
        {"namespace": "NS2", "key": "key2", "value": "val2"},
        {"namespace": "NS3", "key": "key3", "value": "val3"},
        {"namespace": "NS1", "key": "key3", "value": "val3"},
        {"namespace": None, "key": "key4", "value": "val4"},
        {"namespace": None, "key": "key5", "value": None},
    ],
]

HOST_READ_ALLOWED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-read-write.json",
    "tests/helpers/rbac-mock-data/inv-read-only.json",
    "tests/helpers/rbac-mock-data/inv-admin.json",
    "tests/helpers/rbac-mock-data/inv-hosts-splat.json",
    "tests/helpers/rbac-mock-data/inv-star-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-groups-write.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
)
HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-write-only.json",
    "tests/helpers/rbac-mock-data/inv-star-write.json",
    "tests/helpers/rbac-mock-data/inv-groups-read-only.json",
    "tests/helpers/rbac-mock-data/inv-groups-write-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-groups-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-only.json",
    "tests/helpers/rbac-mock-data/inv-groups-splat.json",
)
HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-read-write.json",
    "tests/helpers/rbac-mock-data/inv-write-only.json",
    "tests/helpers/rbac-mock-data/inv-admin.json",
    "tests/helpers/rbac-mock-data/inv-hosts-splat.json",
    "tests/helpers/rbac-mock-data/inv-star-write.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-groups-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-only.json",
)
HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-read-only.json",
    "tests/helpers/rbac-mock-data/inv-star-read.json",
    "tests/helpers/rbac-mock-data/inv-groups-read-only.json",
    "tests/helpers/rbac-mock-data/inv-groups-write-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-groups-write.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
    "tests/helpers/rbac-mock-data/inv-groups-splat.json",
)

GROUP_READ_ALLOWED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-admin.json",
    "tests/helpers/rbac-mock-data/inv-groups-read-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-groups-read.json",
    "tests/helpers/rbac-mock-data/inv-read-only.json",
    "tests/helpers/rbac-mock-data/inv-star-read.json",
    "tests/helpers/rbac-mock-data/inv-groups-splat.json",
)
GROUP_READ_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-groups-write-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-groups-write.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-splat.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-only.json",
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-star-write.json",
    "tests/helpers/rbac-mock-data/inv-write-only.json",
)
GROUP_WRITE_ALLOWED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-admin.json",
    "tests/helpers/rbac-mock-data/inv-groups-write-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-groups-write.json",
    "tests/helpers/rbac-mock-data/inv-read-write.json",
    "tests/helpers/rbac-mock-data/inv-star-write.json",
    "tests/helpers/rbac-mock-data/inv-groups-splat.json",
)
GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-groups-read-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-splat.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-groups-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-only.json",
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-read-only.json",
    "tests/helpers/rbac-mock-data/inv-star-read.json",
)
STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-groups-read-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-splat.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-groups-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-only.json",
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-read-only.json",
    "tests/helpers/rbac-mock-data/inv-star-read.json",
    "tests/helpers/rbac-mock-data/inv-staleness-write-only.json",
)
STALENESS_READ_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
    "tests/helpers/rbac-mock-data/inv-staleness-read-only.json",
    "tests/helpers/rbac-mock-data/inv-staleness-write-only.json",
)
STALENESS_READ_ALLOWED_RBAC_RESPONSE_FILES = ("tests/helpers/rbac-mock-data/inv-staleness-hosts-read-only.json",)
STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES = ("tests/helpers/rbac-mock-data/inv-staleness-hosts-write-only.json",)
RBAC_ADMIN_PROHIBITED_RBAC_RESPONSE_FILES = (
    "tests/helpers/rbac-mock-data/inv-read-write.json",
    "tests/helpers/rbac-mock-data/inv-read-only.json",
    "tests/helpers/rbac-mock-data/inv-admin.json",
    "tests/helpers/rbac-mock-data/inv-hosts-splat.json",
    "tests/helpers/rbac-mock-data/inv-star-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-groups-write.json",
    "tests/helpers/rbac-mock-data/inv-hosts-read-only.json",
    "tests/helpers/rbac-mock-data/inv-none.json",
    "tests/helpers/rbac-mock-data/inv-write-only.json",
    "tests/helpers/rbac-mock-data/inv-star-write.json",
    "tests/helpers/rbac-mock-data/inv-groups-read-only.json",
    "tests/helpers/rbac-mock-data/inv-groups-write-only.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-groups-read.json",
    "tests/helpers/rbac-mock-data/inv-hosts-write-only.json",
    "tests/helpers/rbac-mock-data/inv-groups-splat.json",
)

DEFAULT_STALENESS_SETTINGS = {
    "stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
    "stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}
_INPUT_DATA = {
    "conventional_time_to_stale": DEFAULT_STALENESS_SETTINGS["stale"],
    "conventional_time_to_stale_warning": DEFAULT_STALENESS_SETTINGS["stale_warning"],
    "conventional_time_to_delete": DEFAULT_STALENESS_SETTINGS["delete"],
}


def do_request(
    func: Callable[..., Response],
    url: str,
    identity: dict[str, Any],
    data: dict[str, Any] | None = None,
    query_parameters: dict[str, Any] | None = None,
    extra_headers: dict[str, Any] | None = None,
) -> tuple[int, dict]:
    url = inject_qs(url, **query_parameters) if query_parameters else url
    headers = get_required_headers(identity)

    print("Required Headers: %s", headers)

    if extra_headers:
        headers = {**headers, **extra_headers}

    if func.__name__ in ("post", "patch", "put"):
        response = func(url, data=json.dumps(data), headers=headers)
    else:
        response = func(url, headers=headers)

    try:
        response_data = json.loads(response.content)
    except ValueError:
        response_data = {}

    return response.status_code, response_data


def get_valid_auth_header(identity: dict[str, Any]) -> dict[str, Any]:
    if identity["type"] in IdentityType.__members__.values():
        return build_account_auth_header(identity)

    return build_token_auth_header()


def get_required_headers(identity: dict[str, Any]) -> dict[str, Any]:
    headers = get_valid_auth_header(identity)
    headers["content-type"] = "application/json"

    return headers


def build_account_auth_header(identity: dict[str, Any]) -> dict[str, bytes]:
    dict_ = {"identity": identity}

    json_doc = json.dumps(dict_)
    auth_header = {"x-rh-identity": b64encode(json_doc.encode())}
    return auth_header


def build_token_auth_header(token: str = SHARED_SECRET) -> dict[str, str]:
    auth_header = {"Authorization": f"Bearer {token}"}
    return auth_header


def get_host_from_response(response, index=0):
    return response["results"][index]


def get_host_from_multi_response(response, host_index=0):
    return response["data"][host_index]


def assert_host_was_updated(original_host, updated_host):
    assert updated_host["status"] == 200
    assert updated_host["host"]["id"] == original_host["host"]["id"]
    assert updated_host["host"]["updated"] is not None
    created_time = dateutil.parser.parse(original_host["host"]["created"])
    modified_time = dateutil.parser.parse(updated_host["host"]["updated"])
    assert modified_time > created_time


def assert_host_was_created(create_host_response):
    assert create_host_response["status"] == 201
    created_time = dateutil.parser.parse(create_host_response["host"]["created"])
    current_timestamp = now()
    assert current_timestamp > created_time
    assert (current_timestamp - timedelta(minutes=15)) < created_time


def assert_response_status(response_status, expected_status=200):
    assert response_status == expected_status


def assert_host_response_status(response, expected_status=201, host_index=None):
    host = response
    if host_index is not None:
        host = response["data"][host_index]

    assert host["status"] == expected_status


def assert_host_ids_in_response(response, expected_hosts):
    response_ids = sorted(host["id"] for host in response["results"])
    expected_ids = sorted(str(host.id) for host in expected_hosts)
    assert response_ids == expected_ids


def assert_host_data(actual_host, expected_host, expected_id=None):
    assert actual_host["id"] is not None
    if expected_id:
        assert actual_host["id"] == expected_id
    assert actual_host["account"] == expected_host.account
    assert actual_host["insights_id"] == expected_host.insights_id
    assert actual_host["subscription_manager_id"] == expected_host.subscription_manager_id
    assert actual_host["satellite_id"] == expected_host.satellite_id
    assert actual_host["bios_uuid"] == expected_host.bios_uuid
    assert actual_host["fqdn"] == expected_host.fqdn
    assert actual_host["mac_addresses"] == expected_host.mac_addresses
    assert actual_host["ip_addresses"] == expected_host.ip_addresses
    assert actual_host["ansible_host"] == expected_host.ansible_host
    assert actual_host["created"] is not None
    assert actual_host["updated"] is not None
    if expected_host.facts:
        assert actual_host["facts"] == expected_host.facts
    else:
        assert actual_host["facts"] == []
    if expected_host.display_name:
        assert actual_host["display_name"] == expected_host.display_name
    elif expected_host.fqdn:
        assert actual_host["display_name"] == expected_host.fqdn
    else:
        assert actual_host["display_name"] == actual_host["id"]


def assert_error_response(
    response, expected_title=None, expected_status=None, expected_detail=None, expected_type=None
):
    def _verify_value(field_name, expected_value):
        assert field_name in response
        if expected_value is not None:
            assert response[field_name] == expected_value

    _verify_value("title", expected_title)
    _verify_value("status", expected_status)
    _verify_value("detail", expected_detail)
    _verify_value("type", expected_type)


def assert_tags_response(response_data, expected_response):
    assert len(response_data["results"].keys()) == len(expected_response.keys())
    for host_id, tags in expected_response.items():
        assert len(response_data["results"][host_id]) == len(tags)


def assert_tag_counts(response_data, expected_response):
    assert len(response_data["results"].keys()) == len(expected_response.keys())
    for host_id, tag_count in expected_response.items():
        assert response_data["results"][host_id] == tag_count


def assert_paginated_response_counts(response_data, expected_per_page, expected_total, num_pages):
    # Check if it is the last page to calculate the correct number of returned items
    if response_data["page"] == num_pages:
        last_page_per_page = expected_total % expected_per_page
        if last_page_per_page > 0:
            expected_per_page = last_page_per_page

    assert response_data["total"] == expected_total
    assert response_data["count"] == expected_per_page
    assert len(response_data["results"]) == expected_per_page


def assert_assign_rule_response(response_data, expected_data):
    assert response_data["name"] == expected_data["name"]
    assert response_data["description"] == expected_data["description"]
    assert response_data["group_id"] == expected_data["group_id"]
    assert response_data["filter"] == expected_data["filter"]
    assert response_data["enabled"] == expected_data["enabled"]
    assert "created" in response_data
    assert "modified" in response_data


def api_per_page_test(api_get, subtests, url, per_page, num_pages):
    for page in range(1, num_pages):
        with subtests.test(page=page, per_page=per_page):
            response_status, response_data = api_get(url, query_parameters={"page": page, "per_page": per_page})
            yield response_status, response_data


def api_pagination_invalid_parameters_test(api_get, subtests, url):
    for parameter, invalid_value in product(("per_page", "page"), ("-1", "0", "notanumber")):
        with subtests.test(parameter=parameter, invalid_value=invalid_value):
            response_status, response_data = api_get(url, query_parameters={parameter: invalid_value})
            assert response_status == 400


def api_pagination_index_test(api_get, url, expected_total):
    non_existent_page = expected_total + 1
    response_status, response_data = api_get(url, query_parameters={"page": non_existent_page, "per_page": 1})
    assert response_status == 404


def api_base_pagination_test(
    api_get, subtests, url, expected_total, expected_per_page=1, expected_responses=None, response_match_func=None
):
    num_pages = math.ceil(expected_total / expected_per_page)
    for response_status, response_data in api_per_page_test(api_get, subtests, url, expected_per_page, num_pages):
        assert_response_status(response_status, expected_status=200)
        assert_paginated_response_counts(response_data, expected_per_page, expected_total, num_pages)
        if expected_responses and callable(response_match_func):
            expected_response = expected_responses[response_data["page"] - 1]
            response_match_func(response_data, expected_response)


def api_pagination_test(api_get, subtests, url, expected_total, expected_per_page=1):
    api_base_pagination_test(api_get, subtests, url, expected_total, expected_per_page)
    api_pagination_invalid_parameters_test(api_get, subtests, url)
    if expected_total > 0:
        api_pagination_index_test(api_get, url, expected_total)


def api_tags_pagination_test(api_get, subtests, url, expected_total, expected_per_page=1, expected_responses=None):
    api_base_pagination_test(
        api_get, subtests, url, expected_total, expected_per_page, expected_responses, assert_tags_response
    )


def api_tags_count_pagination_test(
    api_get, subtests, url, expected_total, expected_per_page=1, expected_responses=None
):
    api_base_pagination_test(
        api_get, subtests, url, expected_total, expected_per_page, expected_responses, assert_tag_counts
    )


def api_query_test(api_get, subtests, url, expected_host_list):
    response_status, response_data = api_get(url)

    total_expected = len(expected_host_list)
    host_data = build_expected_host_list(expected_host_list)

    assert response_data["count"] == total_expected
    assert len(response_data["results"]) == total_expected
    assert len(response_data["results"]) == len(host_data)

    api_pagination_test(api_get, subtests, url, expected_total=total_expected)


def build_expected_host_list(host_list):
    host_list.reverse()
    return [
        {key: value for key, value in host.data().items() if key not in ("tags", "system_profile")}
        for host in host_list
    ]


# Since python3.6, dicts retain key order, so asserting that a list of dicts is equal
# doesn't work unless we're certain that the keys are going to be in the same order.
def assert_host_lists_equal(expected_host_list, actual_host_list):
    for i in range(len(expected_host_list)):
        # Don't compare host.groups, as serialized output will be different
        if expected_host_list[i].get("groups"):
            assert expected_host_list[i]["groups"][0]["id"] == actual_host_list[i]["groups"][0]["id"]
            assert expected_host_list[i]["groups"][0]["ungrouped"] == actual_host_list[i]["groups"][0]["ungrouped"]
            assert expected_host_list[i]["groups"][0]["name"] == actual_host_list[i]["groups"][0]["name"]
        expected_host_list[i].pop("groups")
        actual_host_list[i].pop("groups")
        assert expected_host_list[i] == actual_host_list[i]


def build_order_query_parameters(order_by=None, order_how=None):
    query_parameters = {}
    if order_by:
        query_parameters["order_by"] = order_by
    if order_how:
        query_parameters["order_how"] = order_how

    return query_parameters


def build_fields_query_parameters(fields=None):
    query_parameters = {}
    if fields:
        query_parameters["fields"] = fields

    return query_parameters


def _build_url(
    base_url: str = HOST_URL, path: str | None = None, id_list: str | None = None, query: str | None = None
) -> str:
    url = base_url

    if id_list:
        url = f"{url}/{id_list}"

    if path:
        url = f"{url}{path}"

    if query:
        url = f"{url}{query}"

    return url


def build_hosts_url(
    host_list_or_id: list[str] | list[HostWrapper | Host] | str | UUID | None = None,
    path: str | None = None,
    query: str | None = None,
) -> str:
    if host_list_or_id is not None:
        host_list_or_id = build_id_list_for_url(host_list_or_id)

    return _build_url(id_list=host_list_or_id, path=path, query=query)


def build_host_exists_url(insights_id):
    return _build_url(base_url=HOST_EXISTS_URL, query=f"?insights_id={insights_id}")


def build_host_checkin_url():
    return build_hosts_url(path="/checkin")


def build_host_tags_url(host_list_or_id, query=None):
    return build_hosts_url(path="/tags", host_list_or_id=host_list_or_id, query=query)


def build_tags_count_url(host_list_or_id, query=None):
    return build_hosts_url(path="/tags/count", host_list_or_id=host_list_or_id, query=query)


def build_tags_url(query=None):
    return _build_url(base_url=TAGS_URL, query=query)


def build_system_profile_url(host_list_or_id, query=None):
    return build_hosts_url(path="/system_profile", host_list_or_id=host_list_or_id, query=query)


def build_system_profile_sap_system_url(query=None):
    return _build_url(base_url=SYSTEM_PROFILE_URL, path="/sap_system", query=query)


def build_system_profile_sap_sids_url(query=None):
    return _build_url(base_url=SYSTEM_PROFILE_URL, path="/sap_sids", query=query)


def build_system_profile_operating_system_url(query=None):
    return _build_url(base_url=SYSTEM_PROFILE_URL, path="/operating_system", query=query)


def build_facts_url(host_list_or_id, namespace, query=None):
    return build_hosts_url(path=f"/facts/{namespace}", host_list_or_id=host_list_or_id, query=query)


def build_id_list_for_url(id_or_id_list: list[str] | list[HostWrapper | Host] | str | UUID) -> str:
    if isinstance(id_or_id_list, list):
        # check if the list contains hosts or strings
        if not any(isinstance(item, str) for item in id_or_id_list):
            return ",".join(get_id_list_from_hosts(id_or_id_list))  # type: ignore[arg-type]
        else:
            return ",".join(id_or_id_list)  # type: ignore[arg-type]

    return str(id_or_id_list)


def build_groups_url(group_id=None, query=None):
    return _build_url(base_url=GROUP_URL, id_list=group_id, query=query)


def build_resource_types_url(query=None):
    return _build_url(base_url=RESOURCE_TYPES_URL, query=query)


def build_resource_types_groups_url(query=None):
    return _build_url(base_url=RESOURCE_TYPES_URL + "/inventory-groups", query=query)


def get_id_list_from_hosts(host_list: list[HostWrapper | Host]) -> list[str]:
    return [str(h.id) for h in host_list]


def build_staleness_url(path=None, query=None):
    return _build_url(base_url=STALENESS_URL, path=path, query=query)


def build_sys_default_staleness_url(path=None, query=None):
    return _build_url(base_url=STALENESS_URL + "/defaults", path=path, query=query)


def inject_qs(url, **kwargs):
    scheme, netloc, path, query, fragment = urlsplit(url)
    params = parse_qs(query)
    params.update(kwargs)
    new_query = urlencode(params, doseq=True)
    return urlunsplit((scheme, netloc, path, new_query, fragment))


def quote(*args, **kwargs):
    return url_quote(str(args[0]), *args[1:], safe="", **kwargs)


def quote_everything(string):
    encoded = string.encode()
    codes = unpack(f"{len(encoded)}B", encoded)
    return "".join(f"%{code:02x}" for code in codes)


def create_mock_rbac_response(permissions_response_file):
    with open(permissions_response_file) as rbac_response:
        resp_data = json.load(rbac_response)
        return resp_data["data"]


class RBACFilterOperation(str, Enum):
    EQUAL = "equal"
    IN = "in"

    def __str__(self):
        return self.value


def create_custom_rbac_response(
    group_ids: list, operation: RBACFilterOperation = RBACFilterOperation.IN, hosts_permission: str = "read"
) -> list:
    """
    Create a custom RBAC response with a single resource definition.
    This is useful for testing specific RBAC scenarios.
    """

    value = group_ids[0] if operation == RBACFilterOperation.EQUAL and group_ids else group_ids

    return [
        {
            "resourceDefinitions": [
                {
                    "attributeFilter": {
                        "key": "group.id",
                        # flatten the list if operation is "equal"
                        # otherwise, keep it as a list
                        "value": value,
                        "operation": operation,
                    },
                },
            ],
            "permission": "inventory:hosts:" + hosts_permission,
        },
        {"resourceDefinitions": [], "permission": "inventory:groups:read"},
    ]


def assert_group_response(response, expected_group, expected_host_count):
    assert response["id"] == str(expected_group.id)
    assert response["org_id"] == expected_group.org_id
    assert response["account"] == expected_group.account
    assert response["name"] == expected_group.name
    assert response["created"] == expected_group.created_on.isoformat()
    assert response["updated"] == expected_group.modified_on.isoformat()
    assert response["host_count"] == expected_host_count


def assert_resource_types_pagination(
    response_data: dict,
    expected_page: int,
    expected_per_page: int,
    expected_number_of_pages: int,
    expected_path_base: str,
):
    # Assert that the top level fields exist
    assert "meta" in response_data
    assert "links" in response_data
    assert "data" in response_data

    links = response_data["links"]
    assert links["first"] == f"{expected_path_base}?per_page={expected_per_page}&page=1"

    if expected_page > 1:
        assert links["previous"] == f"{expected_path_base}?per_page={expected_per_page}&page={expected_page - 1}"
    else:
        assert links["previous"] is None

    if expected_page < expected_number_of_pages:
        assert links["next"] == f"{expected_path_base}?per_page={expected_per_page}&page={expected_page + 1}"
    else:
        assert links["next"] is None

    assert links["last"] == f"{expected_path_base}?per_page={expected_per_page}&page={expected_number_of_pages}"


def mocked_export_post(_self: Any, url: str, *, data: bytes, **_: Any) -> Response:
    # This will raise UnicodeDecodeError if not correctly encoded or AttributeError if data is str
    data.decode("utf-8")
    response = Response()
    response.url = url
    response.status_code = HTTPStatus.ACCEPTED
    response._content = b"Export successful"
    return response


def mocked_post_workspace_not_found(_self: Any, url: str, **_: Any) -> Response:
    response = Response()
    response.url = url
    response.status_code = HTTPStatus.NOT_FOUND
    response._content = b"Workspace not found"
    return response


def mocked_patch_workspace_name_exists(kessel_response_status: int, _self: Any, url: str, **_: Any) -> Response:
    response = Response()
    response.url = url
    response.status_code = kessel_response_status
    response._content = b'{"detail": "Can\'t patch workspace with same name within same parent workspace"}'
    response.headers = CaseInsensitiveDict({"content-type": "application/json"})
    # Set the response.request attribute which is needed for raise_for_status

    response.request = Request("PATCH", url).prepare()
    return response
