import json
from base64 import b64encode
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from random import randint
from struct import unpack
from urllib.parse import parse_qs
from urllib.parse import quote_plus as url_quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import dateutil.parser

from app.auth.identity import Identity
from app.utils import HostWrapper
from tests.utils import ACCOUNT
from tests.utils import now

HOST_URL = "/api/inventory/v1/hosts"
TAGS_URL = "/api/inventory/v1/tags"
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
SHARED_SECRET = "SuperSecretStuff"


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


def minimal_host(**values):
    data = {
        "account": ACCOUNT,
        "display_name": "hi",
        "ip_addresses": ["10.10.0.1"],
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))).isoformat(),
        "reporter": "test",
        **values,
    }

    return HostWrapper(data)


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


def build_facts_url(host_list, namespace):
    if type(host_list) == list:
        url_host_id_list = build_host_id_list_for_url(host_list)
    else:
        url_host_id_list = str(host_list)
    return f"{HOST_URL}/{url_host_id_list}/facts/{namespace}"


def build_host_id_list_for_url(host_list):
    return ",".join(get_id_list_from_hosts(host_list))


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
