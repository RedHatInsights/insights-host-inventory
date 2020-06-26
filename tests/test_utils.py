import contextlib
import json
import os
import unittest.mock
import uuid
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
from lib.host_repository import find_existing_host

HOST_URL = "/api/inventory/v1/hosts"
TAGS_URL = "/api/inventory/v1/tags"
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

NS = "testns"
ID = "whoabuddy"

ACCOUNT = "000501"
FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
SHARED_SECRET = "SuperSecretStuff"


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


def wrap_message(host_data, operation="add_host", platform_metadata=None):
    message = {"operation": operation, "data": host_data}

    if platform_metadata:
        message["platform_metadata"] = platform_metadata

    return message


@contextlib.contextmanager
def set_environment(new_env=None):
    new_env = new_env or {}
    patched_dict = unittest.mock.patch.dict(os.environ, new_env)
    patched_dict.start()
    os.environ.clear()
    os.environ.update(new_env)
    yield
    patched_dict.stop()


def valid_system_profile():
    return {
        "number_of_cpus": 1,
        "number_of_sockets": 2,
        "cores_per_socket": 4,
        "system_memory_bytes": 1024,
        "infrastructure_type": "massive cpu",
        "infrastructure_vendor": "dell",
        "network_interfaces": [
            {
                "ipv4_addresses": ["10.10.10.1"],
                "state": "UP",
                "ipv6_addresses": ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"],
                "mtu": 1500,
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "type": "loopback",
                "name": "eth0",
            }
        ],
        "disk_devices": [
            {
                "device": "/dev/sdb1",
                "label": "home drive",
                "options": {"uid": "0", "ro": True},
                "mount_point": "/home",
                "type": "ext3",
            }
        ],
        "bios_vendor": "AMI",
        "bios_version": "1.0.0uhoh",
        "bios_release_date": "10/31/2013",
        "cpu_flags": ["flag1", "flag2"],
        "os_release": "Red Hat EL 7.0.1",
        "os_kernel_version": "Linux 2.0.1",
        "arch": "x86-64",
        "last_boot_time": "12:25 Mar 19, 2019",
        "kernel_modules": ["i915", "e1000e"],
        "running_processes": ["vim", "gcc", "python"],
        "subscription_status": "valid",
        "subscription_auto_attach": "yes",
        "katello_agent_running": False,
        "satellite_managed": False,
        "cloud_provider": "Maclean's Music",
        "yum_repos": [
            {"id": "repo1", "name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}
        ],
        "dnf_modules": [{"name": "postgresql", "stream": "11"}, {"name": "java", "stream": "8"}],
        "installed_products": [
            {"name": "eap", "id": "123", "status": "UP"},
            {"name": "jbws", "id": "321", "status": "DOWN"},
        ],
        "insights_client_version": "12.0.12",
        "insights_egg_version": "120.0.1",
        "captured_date": "2020-02-13T12:08:55Z",
        "installed_packages": ["rpm1-0:0.0.1.el7.i686", "rpm1-2:0.0.1.el7.i686"],
        "installed_services": ["ndb", "krb5"],
        "enabled_services": ["ndb", "krb5"],
    }


class MockEventProducer:
    def __init__(self):
        self.event = None
        self.key = None
        self.headers = None
        self.topic = None

    def write_event(self, event, key, headers, topic):
        self.event = event
        self.key = key
        self.headers = headers
        self.topic = topic


def get_host_from_response(response, index=0):
    return response["results"][index]


def get_host_from_multi_response(response, host_index=0):
    return response["data"][host_index]


def minimal_host(**values):
    data = {
        "account": ACCOUNT,
        "display_name": "hi",
        "ip_addresses": ["10.10.0.1"],
        "stale_timestamp": (datetime.now(timezone.utc) + timedelta(days=randint(1, 7))).isoformat(),
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


def assert_host_exists(host_id, search_canonical_facts, account=ACCOUNT):
    found_host = find_existing_host(account, search_canonical_facts)

    assert host_id == found_host.id


def assert_mq_host_data(actual_id, actual_event, expected_results, host_keys_to_check):
    assert actual_event["host"]["id"] == actual_id

    for key in host_keys_to_check:
        assert actual_event["host"][key] == expected_results["host"][key]


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


def generate_uuid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)
