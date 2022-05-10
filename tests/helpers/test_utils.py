import base64
import contextlib
import json
import os
import string
import unittest.mock
import uuid
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from random import choice
from random import randint

from app.utils import HostWrapper

NS = "testns"
ID = "whoabuddy"

SYSTEM_IDENTITY = {
    "account_number": "test",
    "auth_type": "cert-auth",
    "internal": {"auth_time": 6300, "org_id": "3340851"},
    "system": {"cert_type": "system", "cn": "1b36b20f-7fa0-4454-a6d2-008294e06378"},
    "type": "System",
}

USER_IDENTITY = {
    "account_number": "test",
    "org_id": "3340851",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {"email": "tuser@redhat.com", "first_name": "test"},
}

SATELLITE_IDENTITY = deepcopy(SYSTEM_IDENTITY)
SATELLITE_IDENTITY["system"]["cert_type"] = "satellite"


def generate_uuid():
    return str(uuid.uuid4())


def generate_random_string(size=10):
    return "".join(choice(string.ascii_lowercase) for _ in range(size))


def now():
    return datetime.now(timezone.utc)


def get_staleness_timestamps():
    current_timestamp = now()
    return {
        "fresh": current_timestamp + timedelta(hours=1),
        "stale": current_timestamp,
        "stale_warning": current_timestamp - timedelta(weeks=1),
        "culled": current_timestamp - timedelta(weeks=2),
    }


@contextlib.contextmanager
def set_environment(new_env=None):
    new_env = new_env or {}
    patched_dict = unittest.mock.patch.dict(os.environ, new_env)
    patched_dict.start()
    os.environ.clear()
    os.environ.update(new_env)
    yield
    patched_dict.stop()


def minimal_host(**values):
    data = {
        "account": USER_IDENTITY["account_number"],
        "org_id": "3340851",
        "display_name": "test" + generate_random_string(),
        "ip_addresses": ["10.10.0.1"],
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))).isoformat(),
        "reporter": "test" + generate_random_string(),
        **values,
    }
    if "account" in values:
        data["account"] = values.get("account")
    if "org_id" in values:
        data["org_id"] = values.get("org_id")

    return HostWrapper(data)


def valid_system_profile():
    return {
        "owner_id": "afe768a2-1c5e-4480-988b-21c3d6cfacf4",
        "rhc_client_id": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
        "rhc_config_state": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
        "cpu_model": "Intel(R) Xeon(R) CPU E5-2690 0 @ 2.90GHz",
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
        "os_kernel_version": "3.10.0",
        "arch": "x86-64",
        "last_boot_time": "2020-02-13T12:08:55Z",
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
        "gpg_pubkeys": ["gpg-pubkey-11111111-22222222", "gpg-pubkey-33333333-44444444"],
        "installed_services": ["ndb", "krb5"],
        "enabled_services": ["ndb", "krb5"],
        "sap_sids": ["ABC", "DEF", "GHI"],
        "selinux_current_mode": "enforcing",
        "selinux_config_file": "enforcing",
    }


def get_encoded_idstr(identity=SYSTEM_IDENTITY, org_id=None):
    if org_id:
        identity["org_id"] = org_id
    id = {"identity": identity}
    SYSTEM_API_KEY = base64.b64encode(json.dumps(id).encode("utf-8"))

    return SYSTEM_API_KEY.decode("ascii")


def get_platform_metadata(identity=SYSTEM_IDENTITY):
    return {
        "request_id": "b9757340-f839-4541-9af6-f7535edf08db",
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": get_encoded_idstr(identity),
    }


class MockResponseObject:
    def __init__(self):
        self.status_code = 200
        self.content = None

    def json(self):
        return json.loads(self.content)

    def __iter__(self):
        return self

    def __next__(self):
        return self
