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
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
SHARED_SECRET = "SuperSecretStuff"

UUID_1 = "00000000-0000-0000-0000-000000000001"
UUID_2 = "00000000-0000-0000-0000-000000000002"
UUID_3 = "00000000-0000-0000-0000-000000000003"


def do_request(func, url, data=None, query_parameters=None, extra_headers=None, auth_type="account_number"):
    url = inject_qs(url, **query_parameters) if query_parameters else url
    headers = get_required_headers(auth_type)
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


def get_valid_auth_header(auth_type="account_number"):
    if auth_type == "account_number":
        return build_account_auth_header()

    return build_token_auth_header()


def get_required_headers(auth_type="account_number"):
    headers = get_valid_auth_header(auth_type)
    headers["content-type"] = "application/json"

    return headers


def build_account_auth_header(account=ACCOUNT):
    identity = Identity(account_number=account)
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


def api_query_test(api_get, subtests, host_id_list, expected_host_list):
    url = build_hosts_url(host_id_list)
    response_status, response_data = api_get(url)

    total_expected = len(expected_host_list)
    host_data = build_expected_host_list(expected_host_list)

    assert response_data["count"] == total_expected
    assert len(response_data["results"]) == total_expected
    assert len(response_data["results"]) == len(host_data)

    api_pagination_test(api_get, subtests, url, expected_total=total_expected)
    api_pagination_invalid_parameters_test(api_get, subtests, url)

    if total_expected > 0:
        api_pagination_index_test(api_get, url, expected_total=total_expected)


def api_pagination_invalid_parameters_test(api_get, subtests, url):
    for parameter, invalid_value in product(("per_page", "page"), ("-1", "0", "notanumber")):
        with subtests.test(parameter=parameter, invalid_value=invalid_value):
            response_status, response_data = api_get(url, query_parameters={parameter: invalid_value})
            assert response_status == 400


def api_pagination_index_test(api_get, url, expected_total):
    non_existent_page = expected_total + 1
    response_status, response_data = api_get(url, query_parameters={"page": non_existent_page, "per_page": 1})
    assert response_status == 404


def api_pagination_test(api_get, subtests, url, expected_total, expected_per_page=1):
    total_pages = math.ceil(expected_total / expected_per_page)
    for page in range(1, total_pages + 1):
        with subtests.test(page=page):
            response_status, response_data = api_get(
                url, query_parameters={"page": page, "per_page": expected_per_page}
            )
            assert response_status == 200
            assert response_data["total"] == expected_total
            if page == total_pages and total_pages > 1:
                assert response_data["count"] <= expected_per_page
                assert len(response_data["results"]) <= expected_per_page
            else:
                assert response_data["count"] == expected_per_page
                assert len(response_data["results"]) == expected_per_page


def build_expected_host_list(host_list):
    host_list.reverse()
    return [
        {key: value for key, value in host.data().items() if key not in ("tags", "system_profile")}
        for host in host_list
    ]


def build_order_query_parameters(order_by, order_how):
    query_parameters = {}
    if order_by:
        query_parameters["order_by"] = order_by
    if order_how:
        query_parameters["order_how"] = order_how

    return query_parameters


def build_hosts_url(host_list):
    url_host_id_list = build_host_id_list_for_url(host_list)

    return f"{HOST_URL}/{url_host_id_list}"


def build_tags_url(host_list, count=False):
    url_host_id_list = build_host_id_list_for_url(host_list)

    tags_url = f"{HOST_URL}/{url_host_id_list}/tags"

    return f"{tags_url}/count" if count else tags_url


def build_system_profile_url(host_list):
    url_host_id_list = build_host_id_list_for_url(host_list)

    return f"{HOST_URL}/{url_host_id_list}/system_profile"


def build_facts_url(host_list, namespace):
    url_host_id_list = build_host_id_list_for_url(host_list)

    return f"{HOST_URL}/{url_host_id_list}/facts/{namespace}"


def build_host_id_list_for_url(host_list):
    if type(host_list) == dict:
        host_list = list(host_list.values())

    if type(host_list) == list:
        return ",".join(get_id_list_from_hosts(host_list))

    return str(host_list)


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
