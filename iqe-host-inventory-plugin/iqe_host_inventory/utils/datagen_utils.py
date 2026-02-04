from __future__ import annotations

import copy
import datetime
import uuid
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from random import choice
from random import randint
from random import randrange
from string import ascii_letters
from string import digits
from string import punctuation
from typing import Any
from typing import TypedDict

import pytest
from faker import Faker
from faker.providers import internet

fake = Faker()
fake.add_provider(internet)


def rand_str(min_chars: int = 5, max_chars: int = 10) -> str:
    return fake.pystr(min_chars=min_chars, max_chars=max_chars)


_CORRECT_REGISTERED_WITH_VALUES = [
    "puptoo",
    "yupana",
    "rhsm-conduit",
    "cloud-connector",
    "satellite",
    "discovery",
]

_CORRECT_SYSTEM_TYPE_VALUES = ["edge", "conventional", "bootc"]

# System profile field classification constants for table separation
STATIC_SYSTEM_PROFILE_FIELDS = {
    "arch",
    "basearch",
    "bios_release_date",
    "bios_vendor",
    "bios_version",
    "bootc_status",
    "cloud_provider",
    "conversions",
    "cores_per_socket",
    "cpu_model",
    "disk_devices",
    "dnf_modules",
    "enabled_services",
    "gpg_pubkeys",
    "greenboot_fallback_detected",
    "greenboot_status",
    "host_type",
    "image_builder",
    "infrastructure_type",
    "infrastructure_vendor",
    "insights_client_version",
    "installed_packages_delta",
    "installed_services",
    "intersystems",
    "is_marketplace",
    "katello_agent_running",
    "number_of_cpus",
    "number_of_sockets",
    "operating_system",
    "os_kernel_version",
    "os_release",
    "owner_id",
    "public_dns",
    "public_ipv4_addresses",
    "releasever",
    "rhc_client_id",
    "rhc_config_state",
    # Note: rhel_ai removed - it's now only valid inside workloads.rhel_ai
    "rhsm",
    "rpm_ostree_deployments",
    "satellite_managed",
    "selinux_config_file",
    "selinux_current_mode",
    "subscription_auto_attach",
    "subscription_status",
    "system_purpose",
    "system_update_method",
    "third_party_services",
    "threads_per_core",
    "tuned_profile",
    "virtual_host_uuid",
    "yum_repos",
}

DYNAMIC_SYSTEM_PROFILE_FIELDS = {
    "captured_date",
    "running_processes",
    "last_boot_time",
    "installed_packages",
    "network_interfaces",
    "installed_products",
    "cpu_flags",
    "insights_egg_version",
    "kernel_modules",
    "system_memory_bytes",
    "systemd",
    "workloads",
}

DEFAULT_INSIGHTS_ID = "00000000-0000-0000-0000-000000000000"


def get_default_cloud_provider() -> str:
    return "test cloud provider"


def get_default_ansible_host() -> str:
    return "default.test.redhat.com"


class OperatingSystem(TypedDict):
    name: str
    major: int
    minor: int


def generate_operating_system(
    name: str | None = "RHEL", major: int | None = None, minor: int | None = None
) -> OperatingSystem:
    if name is None:
        name = choice(["RHEL", "CentOS Linux"])
    if major is None:
        major = randint(1, 99)
    if minor is None:
        minor = randint(1, 99)
    return OperatingSystem(name=name, major=major, minor=minor)


def get_default_os_rhel() -> OperatingSystem:
    return generate_operating_system(name="RHEL", major=9, minor=4)


def get_default_os_centos() -> OperatingSystem:
    return generate_operating_system("CentOS Linux", 7, 9)


def get_default_operating_system() -> OperatingSystem:
    return get_default_os_rhel()


def get_operating_system_string(operating_system: OperatingSystem | None = None) -> str:
    if operating_system is None:
        operating_system = get_default_operating_system()

    if operating_system["name"] == "RHEL":
        os_name = "Red Hat Enterprise Linux"
    elif operating_system["name"] in ("CentOS", "CentOS Linux"):
        os_name = "CentOS Linux"
    else:
        os_name = operating_system["name"]

    return f"{os_name} release {operating_system['major']}.{operating_system['minor']}"


@dataclass(frozen=True, order=False)
class Field:
    name: str
    type: str  # todo - maybe use python
    item_type: str | None = None  # used when type == array
    is_required: bool = False
    is_canonical: bool = False
    is_id_fact: bool = False
    is_immutable: bool = False

    min_len: int | None = None
    max_len: int | None = None
    min: int | None = None
    max: int | None = None
    dedup_order: int | None = None
    correct_values: list[str] | None = None
    example: Any | None = None
    x_indexed: bool = True


HOST_FIELDS_ = [
    {
        "name": "display_name",
        "type": "str",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
        "min_len": 1,
        "max_len": 200,
    },
    {
        "name": "ansible_host",
        "type": "str",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
        "min_len": 0,
        "max_len": 255,
    },
    {
        "name": "account",
        "type": "str",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
        "min_len": 0,
        "max_len": 10,
    },
    {
        "name": "org_id",
        "type": "str",
        "is_required": True,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
        "min_len": 1,
        "max_len": 36,
    },
    {
        "name": "insights_id",
        "type": "uuid",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": True,
        "is_immutable": False,
        "dedup_order": 3,
    },
    {
        "name": "subscription_manager_id",
        "type": "uuid",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": True,
        "is_immutable": False,
        "dedup_order": 2,
    },
    {
        "name": "satellite_id",
        "type": "sat_uuid",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "fqdn",
        "type": "str",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": False,
        "is_immutable": False,
        "min_len": 1,
        "max_len": 255,
    },
    {
        "name": "bios_uuid",
        "type": "uuid",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "ip_addresses",
        "type": "ip_addr",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "mac_addresses",
        "type": "mac_addr",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "provider_id",
        "type": "str",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": True,
        "is_immutable": True,
        "min_len": 1,
        "max_len": 500,
        "dedup_order": 1,
    },
    {
        "name": "provider_type",
        "type": "enum",
        "is_required": False,
        "is_canonical": True,
        "is_id_fact": False,
        "is_immutable": False,
        "correct_values": ["alibaba", "aws", "azure", "gcp", "ibm"],
    },
    {
        "name": "facts",
        "type": "custom",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "tags",
        "type": "custom",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "system_profile",
        "type": "custom",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "reporter",
        "type": "str",
        "is_required": True,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
        "min_len": 1,
        "max_len": 255,
    },
    {
        "name": "stale_timestamp",
        "type": "timestamp",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
    },
    {
        "name": "openshift_cluster_id",
        "type": "uuid",
        "is_required": False,
        "is_canonical": False,
        "is_id_fact": False,
        "is_immutable": False,
    },
]
HOST_FIELDS = [Field(**item) for item in HOST_FIELDS_]  # type: ignore


SYSTEM_PROFILE_: list[dict[str, Any]] = [
    {"name": "owner_id", "type": "canonical_uuid"},
    {"name": "rhc_client_id", "type": "canonical_uuid"},
    {"name": "rhc_config_state", "type": "canonical_uuid"},
    {"name": "cpu_model", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "number_of_cpus", "type": "int", "min": 0, "max": 2147483647},
    {"name": "number_of_sockets", "type": "int", "min": 0, "max": 2147483647},
    {"name": "cores_per_socket", "type": "int", "min": 0, "max": 2147483647},
    {"name": "threads_per_core", "type": "int", "min": 0, "max": 2147483647},
    {"name": "system_memory_bytes", "type": "int64", "min": 0, "max": 9007199254740991},
    {"name": "infrastructure_type", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "infrastructure_vendor", "type": "str", "min_len": 0, "max_len": 100},
    {
        "name": "network_interfaces",
        "type": "array",
        "item_type": "custom",
        "example": [
            {
                "ipv4_addresses": ["64.233.161.147"],
                "ipv6_addresses": ["0123:4567:89ab:cdef:0123:4567:89ab:cdef"],
                "mtu": 1234,
                "mac_address": "00:00:00:00:00:00",
                "name": "eth0",
                "state": "UP",
                "type": "ether",
            }
        ],
    },
    {
        "name": "disk_devices",
        "type": "array",
        "item_type": "custom",
        "example": [
            {
                "device": "/dev/fdd0",
                "label": "test",
                "mount_point": "/mnt/remote_nfs_shares",
                "type": "ext3",
                "options": {"uid": "0", "ro": "true"},
            }
        ],
    },
    {"name": "bios_vendor", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "bios_version", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "bios_release_date", "type": "str", "min_len": 0, "max_len": 50, "x_indexed": False},
    {"name": "cpu_flags", "type": "array", "item_type": "str", "min_len": 0, "max_len": 30},
    {
        "name": "systemd",
        "type": "custom",
        "example": {"failed": 1, "jobs_queued": 4, "state": "running", "failed_services": ["ex1"]},
    },
    # Note: rhel_ai is NOT a top-level field anymore - it's only valid inside workloads.rhel_ai
    # The legacy rhel_ai structure differs from workloads.rhel_ai, so no backward compatibility
    {"name": "operating_system", "type": "custom", "example": get_default_operating_system()},
    {"name": "os_release", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "os_kernel_version", "type": "custom", "example": "3.10.0"},
    {"name": "arch", "type": "str", "min_len": 0, "max_len": 50},
    {"name": "basearch", "type": "str", "min_len": 0, "max_len": 50},
    {"name": "releasever", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "kernel_modules", "type": "array", "item_type": "str", "min_len": 0, "max_len": 255},
    {"name": "last_boot_time", "type": "date-time"},
    {
        "name": "running_processes",
        "type": "array",
        "item_type": "str",
        "min_len": 0,
        "max_len": 1000,
        "x_indexed": False,
    },
    {"name": "subscription_status", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "subscription_auto_attach", "type": "str", "min_len": 0, "max_len": 100},
    {"name": "katello_agent_running", "type": "bool"},
    {"name": "satellite_managed", "type": "bool"},
    {"name": "cloud_provider", "type": "str", "min_len": 0, "max_len": 100},
    {
        "name": "public_ipv4_addresses",
        "type": "array",
        "item_type": "custom",
        "example": ["12.23.31.32"],
        "x_indexed": False,
    },
    {
        "name": "public_dns",
        "type": "array",
        "item_type": "str",
        "min_len": 0,
        "max_len": 100,
        "example": ["ec2-12-34-56-78.us-west-2.compute.amazonaws.com"],
        "x_indexed": False,
    },
    {
        "name": "yum_repos",
        "type": "array",
        "item_type": "custom",
        "example": [
            {
                "id": "123",
                "name": "test",
                "gpgcheck": True,
                "enabled": False,
                "base_url": "http://localhost",
                "mirrorlist": "https://rhui.redhat.com/pulp/mirror/content/"
                "dist/rhel8/rhui/$releasever/$basearch/baseos/os",
            }
        ],
        "x_indexed": False,
    },
    {
        "name": "dnf_modules",
        "type": "array",
        "item_type": "custom",
        "example": [{"name": "test", "stream": "test_stream"}],
    },
    {
        "name": "installed_products",
        "type": "array",
        "item_type": "custom",
        "example": [{"name": "test", "id": "71", "status": "Subscribed"}],
    },
    {"name": "insights_client_version", "type": "str", "min_len": 0, "max_len": 50},
    {"name": "insights_egg_version", "type": "str", "min_len": 0, "max_len": 50},
    {"name": "captured_date", "type": "date-time"},
    {
        "name": "installed_packages",
        "type": "array",
        "item_type": "str",
        "min_len": 0,
        "max_len": 512,
    },
    {
        "name": "installed_packages_delta",
        "type": "array",
        "item_type": "str",
        "min_len": 0,
        "max_len": 512,
        "x_indexed": False,
    },
    {"name": "gpg_pubkeys", "type": "array", "item_type": "str", "min_len": 0, "max_len": 512},
    {
        "name": "installed_services",
        "type": "array",
        "item_type": "str",
        "min_len": 0,
        "max_len": 512,
    },
    {
        "name": "enabled_services",
        "type": "array",
        "item_type": "str",
        "min_len": 0,
        "max_len": 512,
    },
    {
        "name": "sap",
        "type": "custom",
        "example": {
            "sap_system": True,
            "sids": ["H2O"],
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
        },
    },
    {"name": "sap_system", "type": "bool"},
    {"name": "sap_sids", "type": "array", "item_type": "custom", "example": ["H2O"]},
    {"name": "sap_instance_number", "type": "custom", "example": "03"},
    {"name": "sap_version", "type": "custom", "example": "1.00.122.04.1478575636"},
    {"name": "tuned_profile", "type": "str", "min_len": 0, "max_len": 256},
    {
        "name": "selinux_current_mode",
        "type": "enum",
        "correct_values": ["enforcing", "permissive", "disabled"],
    },
    {"name": "selinux_config_file", "type": "str", "min_len": 0, "max_len": 128},
    {"name": "is_marketplace", "type": "bool"},
    {"name": "host_type", "type": "enum", "correct_values": ["edge"]},
    {"name": "greenboot_status", "type": "enum", "correct_values": ["red", "green"]},
    {"name": "greenboot_fallback_detected", "type": "bool"},
    {
        "name": "rhsm",
        "type": "custom",
        "example": {"version": "8.1", "environment_ids": ["262e621d10ae4475ab5732b39a9160b2"]},
    },
    {
        "name": "rpm_ostree_deployments",
        "type": "array",
        "item_type": "custom",
        "example": [
            {
                "id": "fedora-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ],
    },
    {
        "name": "system_purpose",
        "type": "custom",
        "example": {
            "usage": "Production",
            "role": "Red Hat Enterprise Linux Server",
            "sla": "Premium",
        },
    },
    {
        "name": "ansible",
        "type": "custom",
        "example": {
            "controller_version": "1.2.3",
            "hub_version": "4.5.6",
            "catalog_worker_version": "7.8.9",
            "sso_version": "10.11.12",
        },
    },
    {
        "name": "intersystems",
        "type": "custom",
        "example": {
            "is_intersystems": True,
            "running_instances": [
                {"instance_name": "IRIS3", "product": "IRIS", "version": "2023.1"}
            ],
        },
    },
    {"name": "mssql", "type": "custom", "example": {"version": "15.2.0"}},
    {
        "name": "system_update_method",
        "type": "enum",
        "correct_values": ["dnf", "rpm-ostree", "yum", "bootc"],
    },
    {"name": "virtual_host_uuid", "type": "canonical_uuid"},
    {
        "name": "bootc_status",
        "type": "custom",
        "example": {
            "booted": {
                "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
                "cached_image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
            },
            "rollback": {
                "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
                "cached_image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
            },
            "staged": {
                "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
                "cached_image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
            },
        },
    },
    {"name": "conversions", "type": "custom", "example": {"activity": True}},
    {
        "name": "third_party_services",
        "type": "custom",
        "example": {
            "crowdstrike": {
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": "auto",
                "falcon_version": "7.14.16703.0",
            }
        },
    },
    {
        "name": "image_builder",
        "type": "custom",
        "example": {
            "compliance_policy_id": "89b52baa-9912-4edc-9ed5-be15c06eaaa9",
            "compliance_profile_id": "xccdf_org.ssgproject.content_profile_cis",
        },
    },
    {
        "name": "workloads",
        "type": "custom",
        "example": {
            "ansible": {
                "controller_version": "1.2.3",
                "hub_version": "4.5.6",
                "catalog_worker_version": "7.8.9",
                "sso_version": "1.2.3",
            },
            "crowdstrike": {
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": "auto",
                "falcon_version": "7.14.16703.0",
            },
            "ibm_db2": {
                "is_running": True,
            },
            "intersystems": {
                "is_intersystems": True,
                "running_instances": [
                    {
                        "instance_name": "IRIS3",
                        "product": "IRIS",
                        "version": "2023.1",
                    }
                ],
            },
            "mssql": {
                "version": "15.2.0",
            },
            "oracle_db": {
                "is_running": True,
            },
            "rhel_ai": {
                "variant": "RHEL AI",
                "rhel_ai_version_id": "v1.1.3",
                "gpu_models": [
                    {
                        "name": "NVIDIA A100 80GB PCIe",
                        "vendor": "Nvidia",
                        "memory": "80GB",
                        "count": 4,
                    }
                ],
                "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
                "free_disk_storage": "3TB",
            },
            "sap": {
                "sap_system": True,
                "sids": ["H2O", "ABC", "XYZ"],
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
            },
        },
    },
]


SYSTEM_PROFILE: list[Field] = [Field(**item) for item in SYSTEM_PROFILE_]


def fields_having(
    fields: list[Field], /, condition: Callable[[Field], bool] = (lambda x: True), **parameters
) -> list[Field]:
    return [
        item
        for item in fields
        if condition(item) and all(getattr(item, k) == v for k, v in parameters.items())
    ]


def parametrize_field(
    fields: list[Field],
    condition=(lambda x: True),
    pytest_parameter_name: str = "field",
    **parameters: Any,
):
    if parameters:
        fields = fields_having(fields, condition, **parameters)
    else:
        fields = [item for item in fields if condition(item)]
    return pytest.mark.parametrize(
        pytest_parameter_name, [pytest.param(field, id=field.name) for field in fields]
    )


def get_canonical_facts() -> list[Field]:
    return [field for field in HOST_FIELDS if field.is_canonical]


def get_canonical_not_id_facts() -> list[Field]:
    return [field for field in HOST_FIELDS if field.is_canonical and not field.is_id_fact]


def get_id_facts() -> list[Field]:
    return [field for field in HOST_FIELDS if field.is_id_fact]


def get_id_facts_names() -> list[str]:
    return [field.name for field in get_id_facts()]


def get_immutable_facts() -> list[Field]:
    return [field for field in HOST_FIELDS if field.is_immutable]


def get_mutable_id_facts() -> list[Field]:
    return [field for field in get_id_facts() if not field.is_immutable]


def get_required_fields() -> list[Field]:
    return [field for field in HOST_FIELDS if field.is_required]


def get_host_field_by_name(name: str) -> Field:
    return next(field for field in HOST_FIELDS if field.name == name)


def get_sp_field_by_name(name: str) -> Field:
    return next(field for field in SYSTEM_PROFILE if field.name == name)


def get_sap_fields() -> list[Field]:
    return [field for field in SYSTEM_PROFILE if "sap" in field.name]


def generate_uuid() -> str:
    return str(uuid.uuid4())


def generate_user_identity(org_id: str, account_number: str | int | None = None) -> dict:
    additional_fields = {}
    if account_number is not None:
        additional_fields["account_number"] = account_number
    return {
        "identity": {
            "org_id": org_id,
            "type": "User",
            "auth_type": "basic-auth",
            **additional_fields,
        }
    }


def generate_string_of_length(
    min_length: int,
    max_length: int | None = None,
    use_digits: bool = True,
    use_letters: bool = True,
    use_punctuation: bool = True,
) -> str:
    if max_length is None:
        max_length = min_length
    chars = ""
    if use_digits:
        chars += digits
    if use_letters:
        chars += ascii_letters
    if use_punctuation:
        chars += punctuation
    return "".join(choice(chars) for _ in range(randint(min_length, max_length)))


def generate_digits(min_length, max_length=None) -> str:
    return generate_string_of_length(
        min_length, max_length, use_digits=True, use_letters=False, use_punctuation=False
    )


def generate_fqdn(panic_prevention: str = "hbiqe") -> str:
    return f"{panic_prevention}.{fake.hostname()}"


def generate_display_name(panic_prevention: str = "hbiqe") -> str:
    return f"{panic_prevention}.{generate_uuid()}"


def generate_ips(num_ips: int = 2) -> list[str]:
    """Generate a list of ipv4 IPs."""
    result = []
    for _ in range(0, num_ips):
        result.append(fake.ipv4_private())
    return result


def generate_ipv6s(num_ips: int = 2) -> list[str]:
    """Generate a list of ipv6 IPs."""
    result = []
    for _ in range(0, num_ips):
        result.append(fake.ipv6())
    return result


def generate_macs(num_macs=2):
    """Generate a list of mac addresses."""
    result = []
    for _ in range(0, num_macs):
        result.append(fake.mac_address())
    return result


class FactNamespace(TypedDict):
    namespace: str
    facts: dict[str, str]


def generate_facts(num_facts: int = 2) -> list[FactNamespace]:
    """Generate some facts."""
    facts = {}
    for _ in range(0, num_facts):
        facts[fake.domain_word()] = fake.domain_word()

    result = FactNamespace(namespace=fake.domain_word(), facts=facts)
    return [result]


def generate_tags(num_tags: int = 2) -> list[TagDict]:
    """Generate some tags"""
    result: list[TagDict] = []
    for _ in range(num_tags):
        result.append(gen_tag())
    return result


def generate_random_mac_address(size: int) -> str:
    """
    Helper to generate random mac address.

    :param size: The size of the string in bytes
    :return: mac address in string format
    """
    return ":".join(f"{randrange(256):02x}" for _ in range(size))


class TagDict(TypedDict):
    key: str
    namespace: str | None
    value: str | None


def gen_tag(
    namespace: str | None = None, key: str | None = None, value: str | None = None
) -> TagDict:
    """Returns a structured tag with random missing values."""
    if namespace is None:
        namespace = rand_str()
    if key is None:
        key = rand_str()
    if value is None:
        value = rand_str()
    return TagDict(key=key, namespace=namespace, value=value)


def gen_tag_with_parameters(
    key: str, namespace: str | None = None, value: str | None = None
) -> TagDict:
    """Returns a structured tag."""
    return TagDict(key=key, value=value, namespace=namespace)


def gen_iso8601_datetime(
    start_date: datetime.date | datetime.datetime | datetime.timedelta | str | int = "-10d",
    end_date: datetime.date | datetime.datetime | datetime.timedelta | str | int = "now",
) -> str:
    """Generate a string containing datetime in ISO 8601 format"""
    return fake.date_time_between(
        start_date=start_date, end_date=end_date, tzinfo=datetime.UTC
    ).isoformat()


def gen_stale_timestamp() -> str:
    return gen_iso8601_datetime(start_date="+1d", end_date="+7d")


def get_clamped_timestamp(
    clamp: datetime.date | datetime.datetime | datetime.timedelta | str | int,
):
    return gen_iso8601_datetime(start_date=clamp, end_date=clamp)


def generate_timestamp(
    start_date: datetime.datetime | None = None, delta: datetime.timedelta | None = None
) -> str:
    if start_date is None:
        start_date = datetime.datetime.now(datetime.UTC)
    if delta is None:
        delta = datetime.timedelta(days=randint(1, 7))
    return (start_date + delta).isoformat()


def generate_provider_type() -> str:
    correct_values = get_host_field_by_name("provider_type").correct_values
    assert correct_values is not None
    return choice(correct_values)


def generate_reporter() -> str:
    return choice(_CORRECT_REGISTERED_WITH_VALUES)


def generate_per_reporter_staleness(reporter: str = "iqe-hbi") -> dict[str, dict[str, bool | str]]:
    return {
        reporter: {
            "check_in_succeeded": True,
            "last_check_in": datetime.datetime.now(datetime.UTC).isoformat(),
            "stale_timestamp": generate_timestamp(),
        }
    }


def generate_yum_repo() -> dict[str, str | bool]:
    return {
        "id": generate_string_of_length(0, 256),
        "name": generate_string_of_length(0, 1024),
        "gpgcheck": choice([True, False]),
        "enabled": choice([True, False]),
        "base_url": fake.uri(),
        "mirrorlist": fake.uri(),
    }


def generate_dnf_module() -> dict[str, str]:
    return {
        "name": generate_string_of_length(0, 128),
        "stream": generate_string_of_length(0, 2048),
    }


def generate_installed_product() -> dict[str, str]:
    return {
        "name": generate_string_of_length(0, 512),
        "id": generate_string_of_length(0, 64),
        "status": generate_string_of_length(0, 256),
    }


def generate_sap_sid() -> str:
    first = generate_string_of_length(1, use_punctuation=False, use_digits=False).upper()
    others = generate_string_of_length(2, use_punctuation=False).upper()
    return first + others


def generate_sap_instance_number() -> str:
    return generate_digits(2)


def generate_sap_version() -> str:
    version = generate_digits(1)
    version += f".{generate_digits(2)}"
    version += f".{generate_digits(3)}"
    version += f".{generate_digits(2)}"
    version += f".{generate_digits(10)}"
    return version


def generate_sap() -> dict[str, bool | str | list[str]]:
    return {
        "sap_system": True,
        "sids": [generate_sap_sid() for _ in range(randint(1, 5))],
        "instance_number": generate_sap_instance_number(),
        "version": generate_sap_version(),
    }


def generate_rhsm(totally_random: bool = False) -> dict[str, str | list[str]]:
    version = (
        generate_string_of_length(0, 255)
        if totally_random
        else f"{generate_digits(1)}.{generate_digits(1)}"
    )
    return {
        "version": version,
        "environment_ids": [
            generate_string_of_length(0, 256) if totally_random else uuid.uuid4().hex
            for _ in range(randint(1, 5))
        ],
    }


def create_system_profile_facts():
    return copy.deepcopy(_EXAMPLE_SYSTEM_PROFILE_FACTS)


host_field_generators: dict[str, Callable[[], Any]] = {
    "display_name": generate_display_name,
    "ansible_host": generate_fqdn,
    "account": partial(generate_digits, 10),
    "org_id": partial(generate_digits, 10),
    "insights_id": generate_uuid,
    "subscription_manager_id": generate_uuid,
    "satellite_id": generate_uuid,
    "fqdn": generate_fqdn,
    "bios_uuid": generate_uuid,
    "ip_addresses": generate_ips,
    "mac_addresses": generate_macs,
    "provider_id": generate_uuid,
    "provider_type": generate_provider_type,
    "facts": generate_facts,
    "tags": generate_tags,
    "system_profile": create_system_profile_facts,
    "stale_timestamp": generate_timestamp,
    "reporter": generate_reporter,
    "openshift_cluster_id": generate_uuid,
}


def generate_host_field_value(host_field: Field) -> Any:
    return host_field_generators.get(host_field.name, generate_uuid)()


def generate_sp_field_value(sp_field: Field, gen_array_item: bool = False) -> Any:  # NOQA: C901
    field_type = sp_field.item_type if gen_array_item else sp_field.type
    assert field_type is not None
    field_name = sp_field.name
    assert field_name is not None

    if field_type == "str":
        assert sp_field.min_len is not None
        return generate_string_of_length(sp_field.min_len, sp_field.max_len)
    if "uuid" in field_type:
        return generate_uuid()
    if "int" in field_type:
        assert isinstance(sp_field.min, int)
        assert isinstance(sp_field.max, int)
        return randint(sp_field.min, sp_field.max)
    if field_type == "date-time":
        return generate_timestamp()
    if field_type == "bool":
        return choice([False, True])
    if field_type == "enum":
        assert sp_field.correct_values is not None
        return choice(sp_field.correct_values)

    if field_name == "operating_system":
        return generate_operating_system()
    if field_name == "sap":
        return generate_sap()
    if field_name == "sap_system":
        return choice([True, False])
    if field_name == "sap_instance_number":
        return generate_sap_instance_number()
    if field_name == "sap_version":
        return generate_sap_version()
    if field_name == "rhsm":
        return generate_rhsm()

    if field_type == "array":
        return [generate_sp_field_value(sp_field, True) for _ in range(randint(2, 5))]

    # gen_array_item is True
    if field_name == "yum_repos":
        return generate_yum_repo()
    if field_name == "dnf_modules":
        return generate_dnf_module()
    if field_name == "installed_products":
        return generate_installed_product()
    if field_name == "sap_sids":
        return generate_sap_sid()

    assert sp_field.example is not None
    return copy.deepcopy(sp_field.example[0] if gen_array_item else sp_field.example)


def generate_canonical_facts() -> dict[str, Any]:
    canonical_facts = {}
    for field in get_canonical_facts():
        canonical_facts[field.name] = generate_host_field_value(field)
    return canonical_facts


def create_system_profile_errata() -> dict[str, str | list[str | dict]]:
    return {
        "os_release": generate_sp_field_value(get_sp_field_by_name("os_release")),
        "arch": generate_sp_field_value(get_sp_field_by_name("arch")),
        "yum_repos": [generate_yum_repo() for _ in range(randint(10, 50))],
        "installed_packages": [generate_string_of_length(20, 512) for _ in range(randint(10, 50))],
        "dnf_modules": [generate_dnf_module() for _ in range(randint(3, 20))],
    }


def _sync_direct_workload_fields(
    system_profile: dict[str, Any], workloads: dict[str, Any]
) -> None:
    """Sync ansible, mssql, and intersystems fields from workloads."""
    for field in ("ansible", "mssql", "intersystems"):
        if field in workloads and field in system_profile:
            system_profile[field] = copy.deepcopy(workloads[field])


def _sync_crowdstrike_field(system_profile: dict[str, Any], workloads: dict[str, Any]) -> None:
    """Sync crowdstrike from workloads to third_party_services."""
    if "crowdstrike" not in workloads or "third_party_services" not in system_profile:
        return

    if not isinstance(system_profile["third_party_services"], dict):
        system_profile["third_party_services"] = {}

    system_profile["third_party_services"]["crowdstrike"] = copy.deepcopy(workloads["crowdstrike"])


def _sync_sap_fields(system_profile: dict[str, Any], sap_data: dict[str, Any]) -> None:
    """Sync SAP fields from workloads to individual SAP fields."""
    # Sync nested sap field
    if "sap" in system_profile:
        system_profile["sap"] = copy.deepcopy(sap_data)

    # Sync flat sap fields
    if not isinstance(sap_data, dict):
        return

    sap_field_mappings = {
        "sap_system": "sap_system",
        "sids": "sap_sids",
        "instance_number": "sap_instance_number",
        "version": "sap_version",
    }

    for source_field, target_field in sap_field_mappings.items():
        if source_field in sap_data and target_field in system_profile:
            system_profile[target_field] = copy.deepcopy(sap_data[source_field])


def sync_workloads_with_individual_fields(
    system_profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Synchronize workloads field values with their corresponding individual fields.

    This ensures that:
    - system_profile.ansible matches system_profile.workloads.ansible
    - system_profile.mssql matches system_profile.workloads.mssql
    - system_profile.intersystems matches system_profile.workloads.intersystems
    - system_profile.third_party_services.crowdstrike matches system_profile.workloads.crowdstrike
    - system_profile.sap matches system_profile.workloads.sap (nested)
    - system_profile.sap_* matches system_profile.workloads.sap.* (flat fields)

    Args:
        system_profile: The system profile dictionary to synchronize

    Returns:
        The synchronized system profile dictionary
    """
    if "workloads" not in system_profile:
        return system_profile

    workloads = system_profile["workloads"]

    _sync_direct_workload_fields(system_profile, workloads)
    _sync_crowdstrike_field(system_profile, workloads)

    if "sap" in workloads:
        _sync_sap_fields(system_profile, workloads["sap"])

    return system_profile


def generate_complete_system_profile(
    is_sap_system: bool = False, is_edge: bool = False, is_image_mode: bool = False
) -> dict[str, Any]:
    system_profile = {field.name: generate_sp_field_value(field) for field in SYSTEM_PROFILE}

    if not is_sap_system:
        # Remove SAP from workloads if it exists
        if "workloads" in system_profile and isinstance(system_profile["workloads"], dict):
            system_profile["workloads"].pop("sap", None)
        # Remove individual SAP fields
        for field in get_sap_fields():
            system_profile.pop(field.name)

    if not is_edge:
        system_profile.pop("host_type")

    if not is_image_mode:
        system_profile.pop("bootc_status")

    # Ensure workloads field values match individual field values
    system_profile = sync_workloads_with_individual_fields(system_profile)

    return system_profile


def generate_complete_random_host(
    org_id: str,
    *,
    account_number: str | None = None,
    display_name_prefix: str = "hbiqe",
    include_sp: bool = True,
    is_virtual: bool = True,
    is_sap_system: bool = False,
    is_edge: bool = False,
    is_image_mode: bool = False,
) -> dict[str, Any]:
    host_data = {field.name: generate_host_field_value(field) for field in HOST_FIELDS}

    host_data["org_id"] = org_id
    host_data["account"] = account_number or host_data["account"]
    host_data["display_name"] = generate_display_name(display_name_prefix)

    if not is_virtual:
        host_data.pop("provider_id")
        host_data.pop("provider_type")

    if include_sp:
        host_data["system_profile"] = generate_complete_system_profile(
            is_sap_system, is_edge, is_image_mode
        )
    else:
        host_data.pop("system_profile")

    return host_data


def generate_minimal_host(org_id: str, **extra_fields) -> dict[str, Any]:
    host_data = {field.name: generate_host_field_value(field) for field in get_required_fields()}
    host_data["org_id"] = org_id
    host_data = {**host_data, **extra_fields}

    # At least one ID fact is required
    if not any(field_name in host_data for field_name in get_id_facts_names()):
        host_data["insights_id"] = generate_uuid()

    return host_data


def create_host_data(
    *,
    org_id: str | None = None,
    account_number: str | int | None = None,
    host_type: str | None = None,
    include_sp: bool = True,
    name_prefix: str = "hbiqe",
    **extra_data: Any,
):
    if include_sp:
        data = copy.deepcopy(_EXAMPLE_PAYLOAD_WITH_PROFILE_FACTS)
    else:
        data = copy.deepcopy(_EXAMPLE_PAYLOAD)

    identifiers = generate_uuid()

    if org_id is not None:
        data["org_id"] = org_id
    if account_number is not None:
        data["account"] = account_number

    # host_type has only one valid value; ignore everything else for now
    if host_type is not None and host_type == "edge":
        assert include_sp, "Setting 'host_type' requires 'include_sp' to be True"
        data["system_profile"]["host_type"] = host_type  # type: ignore[index]

    for field in ("insights_id", "subscription_manager_id"):
        data[field] = identifiers

    data["display_name"] = generate_display_name(name_prefix)
    data["ansible_host"] = fake.hostname()
    data["fqdn"] = generate_fqdn(name_prefix)
    data["bios_uuid"] = generate_uuid()

    data["ip_addresses"] = generate_ips()
    data["mac_addresses"] = generate_macs()

    data["facts"] = generate_facts()
    data = {**data, **extra_data}

    return data


_EXAMPLE_SYSTEM_PROFILE_FACTS = {
    "arch": "string",
    "basearch": "string",
    "bios_release_date": "string",
    "bios_vendor": "string",
    "bios_version": "string",
    "cloud_provider": get_default_cloud_provider(),
    "cores_per_socket": 2,
    "cpu_flags": [],
    "disk_devices": [],
    "enabled_services": [],
    "infrastructure_type": "string",
    "infrastructure_vendor": "string",
    "insights_client_version": "string",
    "insights_egg_version": "string",
    "installed_packages": [],
    "installed_products": [],
    "installed_services": [],
    "katello_agent_running": False,
    "kernel_modules": [],
    "last_boot_time": gen_iso8601_datetime(),
    "network_interfaces": [],
    "number_of_cpus": 4,
    "number_of_sockets": 1,
    "operating_system": get_default_operating_system(),
    "os_kernel_version": "3.10.0",
    "os_release": "string",
    "releasever": "string",
    "running_processes": [],
    "satellite_managed": True,
    "subscription_auto_attach": "string",
    "subscription_status": "string",
    "system_memory_bytes": 3,
    "yum_repos": [],
}
_EXAMPLE_PAYLOAD: dict[str, str | int | Sequence[object] | dict[str, object]] = {
    "ansible_host": get_default_ansible_host(),
    "display_name": "new.mydomain.com",
    "org_id": "10203040",
    "insights_id": "40ec059615724ebab7521463757b66a2",
    "subscription_manager_id": "40ec059615724ebab7521463757b66a2",
    "bios_uuid": "40ec059615724ebab7521463757b66a2",
    "fqdn": "some.host.example.com",
    "ip_addresses": ["10.10.0.1", "10.0.0.2"],
    "mac_addresses": ["c2:00:d0:c8:61:01"],
    "facts": [
        {"namespace": "string", "facts": {"fact1": "fact_number_one", "fact2": "fact_number_two"}}
    ],
    "tags": [],
    "reporter": "iqe-hbi",
    "stale_timestamp": gen_stale_timestamp(),  # ESSNTL-5571: Remove this when changes are in Prod
}
_EXAMPLE_PAYLOAD_WITH_PROFILE_FACTS = copy.deepcopy(_EXAMPLE_PAYLOAD)
_EXAMPLE_PAYLOAD_WITH_PROFILE_FACTS["system_profile"] = _EXAMPLE_SYSTEM_PROFILE_FACTS


def generate_static_profile_test_data() -> dict[str, Any]:
    """
    Generate test data for static system profile fields.

    Returns a dictionary containing sample values for all static system profile fields
    that are stored in the system_profiles_static table.
    """
    # Get complete system profile facts
    complete_profile = generate_complete_system_profile()

    # Filter to only static fields
    static_profile = {}
    for field_name in STATIC_SYSTEM_PROFILE_FIELDS:
        if field_name in complete_profile:
            static_profile[field_name] = complete_profile[field_name]

    return static_profile


def generate_dynamic_profile_test_data() -> dict[str, Any]:
    """
    Generate test data for dynamic system profile fields.

    Returns a dictionary containing sample values for all dynamic system profile fields
    that are stored in the system_profiles_dynamic table.
    """

    # Get complete system profile facts
    complete_profile = generate_complete_system_profile()

    # Filter to only dynamic fields
    dynamic_profile = {}
    for field_name in DYNAMIC_SYSTEM_PROFILE_FIELDS:
        if field_name in complete_profile:
            dynamic_profile[field_name] = complete_profile[field_name]

    return dynamic_profile
