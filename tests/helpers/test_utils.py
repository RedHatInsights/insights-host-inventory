import base64
import contextlib
import json
import os
import random
import string
import unittest.mock
import uuid
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from random import choice
from random import randint

from app.models import ProviderType
from app.utils import HostWrapper
from lib.host_repository import COMPOUND_CANONICAL_FACTS_MAP

NS = "testns"
ID = "whoabuddy"

SYSTEM_IDENTITY = {
    "account_number": "test",
    "org_id": "test",
    "auth_type": "cert-auth",
    "internal": {"auth_time": 6300, "org_id": "test"},
    "system": {"cert_type": "system", "cn": "1b36b20f-7fa0-4454-a6d2-008294e06378"},
    "type": "System",
}

USER_IDENTITY = {
    "account_number": "test",
    "org_id": "test",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {"email": "tuser@redhat.com", "first_name": "test"},
}

SERVICE_ACCOUNT_IDENTITY = {
    "account_number": "123",
    "org_id": "456",
    "auth_type": "jwt-auth",
    "internal": {"auth_time": 500, "cross_access": False, "org_id": "456"},
    "service_account": {
        "client_id": "b69eaf9e-e6a6-4f9e-805e-02987daddfbd",
        "username": "service-account-b69eaf9e-e6a6-4f9e-805e-02987daddfbd",
    },
    "type": "ServiceAccount",
}

YUM_REPO1 = {"id": "repo1", "name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}

YUM_REPO2 = {"id": "repo2", "name": "repo2", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}

SATELLITE_IDENTITY = deepcopy(SYSTEM_IDENTITY)
SATELLITE_IDENTITY["system"]["cert_type"] = "satellite"

COMPOUND_FACT_VALUES = {"provider_type": ProviderType.AWS}


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


def _base_host_data(**values):
    return {
        "org_id": USER_IDENTITY["org_id"],
        "display_name": "test" + generate_random_string(),
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))).isoformat(),
        "reporter": "test" + generate_random_string(),
        **values,
    }


# This method returns a host wrapper that doesn't contain any canonical facts.
# It should be used in test cases that explicitly set canonical facts.
def base_host(**values):
    return HostWrapper(_base_host_data(**values))


# This method returns a host wrapper that contains a single canonical fact, making it
# a minimal host that's valid for use with mq_create_or_update_host().
# It should be used in test cases where specific canonical facts are not needed.
def minimal_host(**values):
    host_wrapper = HostWrapper(_base_host_data(**values))
    host_wrapper.bios_uuid = generate_uuid()
    return host_wrapper


def valid_system_profile(owner_id=None, additional_yum_repo=None):
    system_profile = {
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
        "yum_repos": [YUM_REPO1],
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
        "system_update_method": "yum",
    }

    if additional_yum_repo:
        system_profile["yum_repos"].append(additional_yum_repo)

    if owner_id:
        system_profile["owner_id"] = owner_id

    return system_profile


def get_encoded_idstr(identity=SYSTEM_IDENTITY):
    id = {"identity": identity}
    SYSTEM_API_KEY = base64.b64encode(json.dumps(id).encode("utf-8"))

    return SYSTEM_API_KEY.decode("ascii")


def get_platform_metadata(identity=SYSTEM_IDENTITY):
    return {
        "request_id": "b9757340-f839-4541-9af6-f7535edf08db",
        "archive_url": "http://s3.aws.com/redhat/insights/1234567",
        "b64_identity": get_encoded_idstr(identity),
    }


def random_mac():
    return "{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}".format(
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
    )


def generate_mac_addresses(num_mac):
    macs = []
    for i in range(num_mac):
        macs.append(random_mac())
    return macs


# Extend this method as new types are required.
def generate_fact(fact_name, num=1):
    if fact_name == "mac_addresses":
        return generate_mac_addresses(num)
    return generate_uuid()


def generate_fact_dict(fact_name, num=1):
    fact_dict = {fact_name: generate_fact(fact_name, num)}
    if compound_fact := COMPOUND_CANONICAL_FACTS_MAP.get(fact_name):
        fact_dict[compound_fact] = COMPOUND_FACT_VALUES[compound_fact]

    return fact_dict


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
