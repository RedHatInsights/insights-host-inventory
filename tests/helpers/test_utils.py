from __future__ import annotations

import base64
import contextlib
import json
import os
import random
import string
import unittest.mock
import uuid
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from random import choice
from random import randint
from typing import Any

from app.config import COMPOUND_ID_FACTS_MAP
from app.config import ID_FACTS
from app.models import ProviderType
from app.utils import HostWrapper

NS = "testns"
ID = "whoabuddy"

SYSTEM_IDENTITY: dict[str, Any] = {
    "account_number": "test",
    "org_id": "test",
    "auth_type": "cert-auth",
    "internal": {"auth_time": 6300, "org_id": "test"},
    "system": {"cert_type": "system", "cn": "1b36b20f-7fa0-4454-a6d2-008294e06378"},
    "type": "System",
}

USER_IDENTITY: dict[str, Any] = {
    "account_number": "test",
    "org_id": "test",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {"email": "tuser@redhat.com", "first_name": "test", "username": "tuser@redhat.com"},
}

SERVICE_ACCOUNT_IDENTITY: dict[str, Any] = {
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

X509_IDENTITY: dict[str, Any] = {
    "type": "X509",
    "auth_type": "X509",
    "x509": {
        "subject_dn": "/CN=some-host.example.com",
        "issuer_dn": "/CN=certificate-authority.example.com",
    },
}

RHSM_ERRATA_IDENTITY_PROD = deepcopy(X509_IDENTITY)
RHSM_ERRATA_IDENTITY_PROD["x509"]["subject_dn"] = "/O=mpaas/OU=serviceaccounts/UID=mpp:rhsm:prod-errata-notifications"
RHSM_ERRATA_IDENTITY_PROD["x509"]["issuer_dn"] = "/O=Red Hat/OU=prod/CN=2023 Certificate Authority RHCSv2"

RHSM_ERRATA_IDENTITY_STAGE = deepcopy(RHSM_ERRATA_IDENTITY_PROD)
RHSM_ERRATA_IDENTITY_STAGE["x509"]["subject_dn"] = (
    "/O=mpaas/OU=serviceaccounts/UID=mpp:rhsm:nonprod-errata-notifications"
)

YUM_REPO1 = {"id": "repo1", "name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}

YUM_REPO2 = {"id": "repo2", "name": "repo2", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}

SATELLITE_IDENTITY = deepcopy(SYSTEM_IDENTITY)
SATELLITE_IDENTITY["system"]["cert_type"] = "satellite"

COMPOUND_FACT_VALUES = {"provider_type": ProviderType.AWS.value}

CANONICAL_FACTS_LIST = (
    "provider_id",
    "provider_type",
    "subscription_manager_id",
    "insights_id",
    "satellite_id",
    "fqdn",
    "bios_uuid",
    "ip_addresses",
    "mac_addresses",
)


def generate_uuid():
    return str(uuid.uuid4())


def generate_random_string(size=10):
    return "".join(choice(string.ascii_lowercase) for _ in range(size))


def now():
    return datetime.now(UTC)


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


def _base_host_data(**values) -> dict[str, Any]:
    return {
        "org_id": USER_IDENTITY["org_id"],
        "display_name": "test" + generate_random_string(),
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))).isoformat(),
        "reporter": "test" + generate_random_string(),
        "created": now().isoformat(),
        **values,
    }


# This method returns a host wrapper that doesn't contain any canonical facts.
# It should be used in test cases that explicitly set canonical facts.
def base_host(**values):
    return HostWrapper(_base_host_data(**values))


# This method returns a host wrapper that contains a single canonical fact, making it
# a minimal host that's valid for use with mq_create_or_update_host().
# It should be used in test cases where specific canonical facts are not needed.
def minimal_host(**values) -> HostWrapper:
    host_wrapper = HostWrapper(_base_host_data(**values))
    if all(id_fact not in values for id_fact in ID_FACTS):
        host_wrapper.subscription_manager_id = generate_uuid()
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
        "workloads": {
            "ansible": {
                "controller_version": "1.2.3",
                "hub_version": "1.2.3",
                "catalog_worker_version": "1.2.3",
                "sso_version": "1.2.3",
            },
            "rhel_ai": {
                "variant": "RHEL AI",
                "rhel_ai_version_id": "v1.1.3",
                "gpu_models": [
                    {
                        "name": "NVIDIA L4",
                        "vendor": "Nvidia",
                        "memory": "24GB",
                        "count": 2,
                    },
                    {
                        "name": "NVIDIA L4",
                        "vendor": "Nvidia",
                        "memory": "16GB",
                        "count": 4,
                    },
                ],
                "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
                "free_disk_storage": "698GB",
            },
        },
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


def random_mac() -> str:
    return (
        f"{random.randint(0, 255):02x}:{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}:{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}:{random.randint(0, 255):02x}"
    )


def random_ip() -> str:
    return ".".join(str(random.randint(0, 255)) for _ in range(4))


def generate_mac_addresses(num_macs: int) -> list[str]:
    return [random_mac() for _ in range(num_macs)]


def generate_ip_addresses(num_ips: int) -> list[str]:
    return [random_ip() for _ in range(num_ips)]


# Extend this method as new types are required.
def generate_fact(fact_name: str, num: int = 1) -> str | list[str]:
    if fact_name == "mac_addresses":
        return generate_mac_addresses(num)
    if fact_name == "ip_addresses":
        return generate_ip_addresses(num)
    if fact_name == "provider_type":
        return choice(list(ProviderType))
    return generate_uuid()


def generate_fact_dict(fact_name, num=1):
    fact_dict = {fact_name: generate_fact(fact_name, num)}
    if compound_fact := COMPOUND_ID_FACTS_MAP.get(fact_name):
        fact_dict[compound_fact] = COMPOUND_FACT_VALUES[compound_fact]

    return fact_dict


def generate_all_canonical_facts() -> dict[str, str | list[str]]:
    return {canonical_fact: generate_fact(canonical_fact) for canonical_fact in CANONICAL_FACTS_LIST}


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


def get_sample_profile_data(org_id, host_id):
    """Returns a dictionary of sample data for creating a dynamic profile."""
    current_time = datetime.now(UTC)
    return {
        "org_id": org_id,
        "host_id": host_id,
        "captured_date": current_time,
        "running_processes": ["sshd", "crond", "systemd"],
        "last_boot_time": current_time - timedelta(days=7),
        "installed_packages": ["kernel-5.14.0", "python3-3.9.7", "openssl-1.1.1k"],
        "network_interfaces": [
            {"name": "eth0", "ipv4_addresses": ["192.168.1.10"], "state": "UP"},
            {"name": "lo", "ipv4_addresses": ["127.0.0.1"], "state": "UNKNOWN"},
        ],
        "installed_products": [{"name": "Red Hat Enterprise Linux", "id": "RHEL-8"}],
        "cpu_flags": ["fpu", "vme", "de", "pse", "tsc"],
        "insights_egg_version": "2.1.3",
        "kernel_modules": ["ext4", "xfs", "btrfs", "i915"],
        "system_memory_bytes": 1024,
        "systemd": {"services_enabled": 52, "services_disabled": 11, "sockets": 15},
        "workloads": {
            "ansible": {
                "controller_version": "4.5.6",
                "hub_version": "4.5.6",
                "catalog_worker_version": "1.2.3",
                "sso_version": "7.8.9",
            },
            "crowdstrike": {
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": "kernel",
                "falcon_version": "7.14.16703.0",
            },
            "ibm_db2": {"is_running": True},
            "intersystems": {
                "is_intersystems": True,
                "running_instances": [
                    {"name": "HEALTH_PROD", "version": "2023.1.0.215.0", "path": "/opt/intersystems/iris/bin"}
                ],
            },
            "mssql": {"version": "15.2.0"},
            "oracle_db": {"is_running": False},
            "rhel_ai": {
                "variant": "RHEL AI",
                "rhel_ai_version_id": "v1.1.3",
                "gpu_models": [{"name": "NVIDIA A100 80GB PCIe", "vendor": "Nvidia", "memory": "80GB", "count": 4}],
                "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
                "free_disk_storage": "698GB",
            },
            "sap": {
                "sap_system": True,
                "sids": ["H2O", "ABC"],
                "instance_number": "03",
                "version": "2.00.122.04.1478575636",
            },
        },
    }
