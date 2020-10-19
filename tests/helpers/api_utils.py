import json
import math
from base64 import b64encode
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from itertools import product
from struct import unpack
from urllib.parse import parse_qs
from urllib.parse import quote_plus as url_quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import dateutil.parser

from app.auth.identity import Identity
from tests.helpers.test_utils import ACCOUNT

HOST_URL = "/api/inventory/v1/hosts"
TAGS_URL = "/api/inventory/v1/tags"
SYSTEM_PROFILE_URL = "/api/inventory/v1/system_profile"

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

UUID_1 = "00000000-0000-0000-0000-000000000001"
UUID_2 = "00000000-0000-0000-0000-000000000002"
UUID_3 = "00000000-0000-0000-0000-000000000003"

READ_ALLOWED_RBAC_RESPONSE_FILES = (
    "utils/rbac-mock-data/inv-read-write.json",
    "utils/rbac-mock-data/inv-read-only.json",
    "utils/rbac-mock-data/inv-admin.json",
    "utils/rbac-mock-data/inv-hosts-splat.json",
    "utils/rbac-mock-data/inv-star-read.json",
)
READ_PROHIBITED_RBAC_RESPONSE_FILES = (
    "utils/rbac-mock-data/inv-none.json",
    "utils/rbac-mock-data/inv-write-only.json",
    "utils/rbac-mock-data/inv-star-write.json",
)
WRITE_ALLOWED_RBAC_RESPONSE_FILES = (
    "utils/rbac-mock-data/inv-read-write.json",
    "utils/rbac-mock-data/inv-write-only.json",
    "utils/rbac-mock-data/inv-admin.json",
    "utils/rbac-mock-data/inv-hosts-splat.json",
    "utils/rbac-mock-data/inv-star-write.json",
)
WRITE_PROHIBITED_RBAC_RESPONSE_FILES = (
    "utils/rbac-mock-data/inv-none.json",
    "utils/rbac-mock-data/inv-read-only.json",
    "utils/rbac-mock-data/inv-star-read.json",
)


def do_request(
    func, url, data=None, query_parameters=None, extra_headers=None, auth_type="account_number", identity_type="User"
):
    url = inject_qs(url, **query_parameters) if query_parameters else url
    headers = get_required_headers(auth_type, identity_type)
    if extra_headers:
        headers = {**headers, **extra_headers}

    if func.__name__ in ("post", "patch", "put"):
        response = func(url, data=json.dumps(data), headers=headers)
    else:
        response = func(url, headers=headers)

    try:
        response_data = json.loads(response.data)
    except ValueError:
        response_data = {}

    return response.status_code, response_data


def get_valid_auth_header(auth_type="account_number", identity_type="User"):
    if auth_type == "account_number":
        return build_account_auth_header(identity_type=identity_type)

    return build_token_auth_header()


def get_required_headers(auth_type="account_number", identity_type="User"):
    headers = get_valid_auth_header(auth_type, identity_type)
    headers["content-type"] = "application/json"

    return headers


def build_account_auth_header(account=ACCOUNT, identity_type="User"):
    identity = Identity(account_number=account, identity_type=identity_type)
    dict_ = {"identity": identity._asdict()}
    json_doc = json.dumps(dict_)
    auth_header = {"x-rh-identity": b64encode(json_doc.encode())}
    return auth_header


def build_token_auth_header(token=SHARED_SECRET):
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
    current_timestamp = datetime.now(timezone.utc)
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
    response_ids = sorted([host["id"] for host in response["results"]])
    expected_ids = sorted([str(host.id) for host in expected_hosts])
    assert response_ids == expected_ids


def assert_host_data(actual_host, expected_host, expected_id=None):
    assert actual_host["id"] is not None
    if expected_id:
        assert actual_host["id"] == expected_id
    assert actual_host["account"] == expected_host.account
    assert actual_host["insights_id"] == expected_host.insights_id
    assert actual_host["rhel_machine_id"] == expected_host.rhel_machine_id
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


def build_order_query_parameters(order_by=None, order_how=None):
    query_parameters = {}
    if order_by:
        query_parameters["order_by"] = order_by
    if order_how:
        query_parameters["order_how"] = order_how

    return query_parameters


def _build_url(base_url=HOST_URL, path=None, host_list_or_id=None, query=None):
    url = base_url

    if host_list_or_id:
        url_host_id_list = build_host_id_list_for_url(host_list_or_id)
        url = f"{url}/{url_host_id_list}"

    if path:
        url = f"{url}{path}"

    if query:
        url = f"{url}{query}"

    return url


def build_hosts_url(host_list_or_id=None, query=None):
    return _build_url(host_list_or_id=host_list_or_id, query=query)


def build_host_checkin_url():
    return _build_url(base_url=HOST_URL, path="/checkin")


def build_host_tags_url(host_list_or_id, query=None):
    return _build_url(path="/tags", host_list_or_id=host_list_or_id, query=query)


def build_tags_count_url(host_list_or_id, query=None):
    return _build_url(path="/tags/count", host_list_or_id=host_list_or_id, query=query)


def build_tags_url(query=None):
    return _build_url(base_url=TAGS_URL, query=query)


def build_system_profile_url(host_list_or_id, query=None):
    return _build_url(path="/system_profile", host_list_or_id=host_list_or_id, query=query)


def build_system_profile_sap_system_url(query=None):
    return _build_url(base_url=SYSTEM_PROFILE_URL, path="/sap_system", query=query)


def build_system_profile_sap_sids_url(query=None):
    return _build_url(base_url=SYSTEM_PROFILE_URL, path="/sap_sids", query=query)


def build_facts_url(host_list_or_id, namespace, query=None):
    return _build_url(path=f"/facts/{namespace}", host_list_or_id=host_list_or_id, query=query)


def build_host_id_list_for_url(host_list_or_id):
    if type(host_list_or_id) == dict:
        host_list_or_id = list(host_list_or_id.values())

    if type(host_list_or_id) == list:
        return ",".join(get_id_list_from_hosts(host_list_or_id))

    return str(host_list_or_id)


def get_id_list_from_hosts(host_list):
    return [str(h.id) for h in host_list]


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
    with open(permissions_response_file, "r") as rbac_response:
        resp_data = json.load(rbac_response)
        return resp_data["data"]
