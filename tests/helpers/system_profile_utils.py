from contextlib import contextmanager
from copy import deepcopy
from os.path import join
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from yaml import safe_dump
from yaml import safe_load

from app.models import SPECIFICATION_DIR
from app.models import SYSTEM_PROFILE_SPECIFICATION_FILE
from app.models import HostSchema
from app.models import LimitedHostSchema

MOCK_DEEPOBJECT_SPEC = {
    "type": "object",
    "properties": {
        "d1n1": {
            "type": "object",
            "properties": {
                "d2n1": {"type": "object", "properties": {"name": {"type": "string", "x-wildcard": True}}},
                "d2n2": {"type": "object", "properties": {"name": {"type": "string", "x-wildcard": True}}},
            },
        },
        "d1n2": {"type": "object", "properties": {"name": {"type": "string", "x-wildcard": True}}},
    },
}


def system_profile_specification():
    file_name = join(SPECIFICATION_DIR, SYSTEM_PROFILE_SPECIFICATION_FILE)
    with open(file_name) as orig_file:
        return safe_load(orig_file)


def system_profile_deep_object_spec():
    orig_spec = system_profile_specification()
    mock_spec = deepcopy(orig_spec)
    mock_spec["$defs"]["SystemProfile"]["properties"]["ansible"]["properties"]["d0n1"] = MOCK_DEEPOBJECT_SPEC
    return mock_spec


def clear_schema_cache():
    try:
        delattr(HostSchema, "system_profile_normalizer")
        delattr(LimitedHostSchema, "system_profile_normalizer")
    except AttributeError:
        pass


@contextmanager
def mock_system_profile_specification(mock_spec):
    clear_schema_cache()

    try:
        with NamedTemporaryFile("w+") as temp_file:
            safe_dump(mock_spec, temp_file)
            with patch("app.models.system_profile_normalizer.SYSTEM_PROFILE_SPECIFICATION_FILE", temp_file.name):
                yield
    finally:
        clear_schema_cache()


INVALID_SYSTEM_PROFILES = (
    {"infrastructure_type": "x" * 101},
    {"infrastructure_vendor": "x" * 101},
    {"network_interfaces": [{"mac_address": "x" * 60}]},
    {"network_interfaces": [{"mac_address": "some-string" * 60}]},
    {"network_interfaces": [{"name": "x" * 51}]},
    {"network_interfaces": [{"state": "x" * 26}]},
    {"network_interfaces": [{"type": "x" * 19}]},
    {"disk_devices": [{"device": "x" * 2049}]},
    {"disk_devices": [{"label": "x" * 1025}]},
    {"disk_devices": [{"options": {"": "XXX"}}]},
    {"disk_devices": [{"mount_point": "x" * 2049}]},
    {"disk_devices": [{"type": "x" * 257}]},
    {"bios_vendor": "x" * 101},
    {"bios_version": "x" * 101},
    {"bios_release_date": "x" * 51},
    {"cpu_flags": ["x" * 31]},
    {"os_release": "x" * 101},
    {"os_kernel_version": "x" * 21},
    {"releasever": "x" * 101},
    {"arch": "x" * 51},
    {"basearch": "x" * 51},
    {"kernel_modules": ["x" * 256]},
    {"last_boot_time": ["x" * 51]},
    {"running_processes": ["x" * 1001]},
    {"subscription_status": ["x" * 101]},
    {"subscription_auto_attach": ["x" * 101]},
    {"cloud_provider": ["x" * 101]},
    {"public_ipv4_addresses": ["x" * 16]},
    {"public_dns": ["x" * 101]},
    {"yum_repos": [{"id": "x" * 257}]},
    {"yum_repos": [{"name": "x" * 1025}]},
    {"yum_repos": [{"base_url": "x" * 2049}]},
    {"yum_repos": [{"mirrorlist": "x" * 2049}]},
    {"dnf_modules": [{"name": "x" * 129}]},
    {"dnf_modules": [{"stream": "x" * 2049}]},
    {"dnf_modules": [{"name": "x", "stream": "y", "status": ["unknown"]}]},
    {"installed_products": [{"name": "x" * 513}]},
    {"installed_products": [{"id": "x" * 65}]},
    {"installed_products": [{"status": "x" * 257}]},
    {"insights_client_version": "x" * 51},
    {"insights_egg_version": "x" * 51},
    {"captured_date": "x" * 51},
    {"installed_packages": ["x" * 513]},
    {"gpg_pubkeys": ["x" * 513]},
    {"installed_services": ["x" * 513]},
    {"enabled_services": ["x" * 513]},
    {
        "sap": {  # Incorrect version, too long
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.147857563665464",
            "sids": ["H2O"],
        }
    },
    {
        "sap": {  # Incorrect version, invalid symbols
            "sap_system": True,
            "instance_number": "03",
            "version": "1-00v122=04a1478575636",
            "sids": ["H2O"],
        }
    },
    {
        "sap": {  # Incorrect instance_number value
            "sap_system": True,
            "instance_number": "300",
            "version": "1.00.122.04.1478575636",
            "sids": ["H2O"],
        }
    },
    {
        "sap": {  # Incorrect sap_system value
            "sap_system": "x",
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["H2O"],
        }
    },
    {
        "sap": {  # Incorrect sids value
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["XXXX"],
        }
    },
    {
        "sap": {  # Incorrect sids value
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["XX"],
        }
    },
    {
        "sap": {  # Incorrect sids value
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["123"],
        }
    },
    {
        "sap": {  # Incorrect sids value
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["abc"],
        }
    },
    {
        "sap": {  # Incorrect sids value
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["ABC", "ABC"],
        }
    },
    {"sap_sids": ["XXXX"]},
    {"sap_sids": ["XX"]},
    {"sap_sids": ["123"]},
    {"sap_sids": ["abc"]},
    {"sap_sids": ["ABC", "ABC"]},
    {"sap_system": "x"},
    {"sap_instance_number": "300"},
    {"sap_version": "1.00.122.04.147857563665464"},
    {"sap_version": "1-00v122=04a1478575636"},
    {"tuned_profile": "x" * 257},
    {"selinux_current_mode": "random"},
    {"selinux_config_file": "x" * 129},
    {"owner_id": "x" * 12},
    {"rhc_client_id": "x" * 12},
    {"rhc_client_id": "plxi13y1-99ut-3rdf-bc10-84opf904lfad"},
    {"rhc_config_state": "x" * 12},
    {"cpu_model": "x" * 101},
    {"number_of_cpus": "2147483648"},
    {"number_of_cpus": 2147483648},
    {"number_of_sockets": 2147483648},
    {"cores_per_socket": 2147483648},
    {"number_of_sockets": "2147483648"},
    {"cores_per_socket": "2147483648"},
    {"system_memory_bytes": "9007199254740992"},
    {"system_memory_bytes": 9007199254740992},
    {"network_interfaces": [{"mtu": 2147483648}]},
    {"network_interfaces": [{"ipv4_addresses": "192.0.2.146"}]},
    {"network_interfaces": [{"ipv6_addresses": "0123:4567:89ab:cdef:0123:4567:89ab:cdef"}]},
    {"network_interfaces": [{"mtu": "15"}]},
    {"rhsm": {"version": "x" * 300}},
    {"rhsm": {"environment_ids": [5]}},  # must be an array of strings
    {"operating_system": {"name": "RHEL"}},  # Incomplete OS definition
    {"operating_system": {"name": "RHEL", "major": 9}},  # Incomplete OS definition
    {"operating_system": {"major": 8, "minor": 7}},  # Incomplete OS definition
    {"operating_system": {"name": "ABCD", "major": 9, "minor": 0}},  # Invalid name
    {"operating_system": {"name": "RHEL", "major": "foo", "minor": "0"}},  # Invalid types
    {"katello_agent_running": "not-a-boolean"},
    {"satellite_managed": "not-a-boolean"},
    {"is_marketplace": "not-a-boolean"},
    {"yum_repos": [{"gpgcheck": "not-a-boolean"}]},
    {"yum_repos": [{"enabled": "not-a-boolean"}]},
    {"installed_packages_delta": ["x" * 513]},
    {"host_type": "nope"},
    {"greenboot_status": "blue"},
    {"greenboot_status": "too long"},
    {"greenboot_fallback_detected": "x"},
    {
        "rpm_ostree_deployments": [
            {  # checksum empty
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # checksum too short
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "3335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # checksum too long
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "663335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # checksum invalid character
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "g3335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # checksum missing
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # id empty
                "id": "",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # id too long
                "id": "x" * 256,
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # id missing
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # origin too long
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "x" * 256,
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # origin missing
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # osname empty
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # osname too long
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "x" * 256,
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # osname missing
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # version empty
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # version too long
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "x" * 256,
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # bad booted
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "booted": "x",
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # bad pinned
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "booted": True,
                "pinned": "x",
            }
        ]
    },
    {
        "bootc_status": {  # bad image, too long string
            "booted": {
                "image": "x" * 129,
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",
                "cached_image": "x" * 129,
                "cached_image_digest": "sha256:654275229d342b2836dcb8e5b851bbb1461b664a9fb9b8c934011e1abf15d778",
            },
            "rollback": {
                "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "image_digest": "sha256:92e476435ced1c148350c660b09c744717defbd300a15d33deda5b50ad6b21a0",
            },
        }
    },
    {
        "bootc_status": {  # bad image_digest, not follow pattern
            "booted": {
                "image": "192.168.124.1:5000/bootc-insights:latest",
                "image_digest": "sha:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",
            }
        }
    },
    {
        "system_purpose": {
            "usage": "foo",
            "role": """Red Hat Enterprise Linux Server for HPC Compute Node,
                    Self-support (Physical or Virtual Node)
                    - and some absurd long fake string suffix""",
            "sla": "baz",
        }
    },
    {
        "ansible": {  # wrong data type for controller_version
            "controller_version": 1.0,
            "hub_version": "3.4.1",
            "catalog_worker_version": "100.387.9846.12",
            "sso_version": "1.28.3.52641.10000513168495123",
        }
    },
    {
        "ansible": {  # sso_version too long
            "controller_version": "1.0",
            "hub_version": "3.4.1",
            "catalog_worker_version": "100.387.9846.12",
            "sso_version": "1.4" * 11,
        }
    },
    {
        "ansible": {  # don't send "existence" booleans in place of versions
            "controller_version": True,
            "hub_version": False,
            "catalog_worker_version": False,
            "sso_version": False,
        }
    },
    {
        "intersystems": {  # Incorrect is_intersystems value
            "is_intersystems": "x",
            "running_instances": [{"instance_name": "IRIS1", "product": "IRIS", "version": "2023.1"}],
        }
    },
    {
        "intersystems": {  # Incorrect instance_name value
            "is_intersystems": True,
            "running_instances": [{"instance_name": "x" * 300, "product": "IRIS", "version": "2023.1"}],
        }
    },
    {
        "intersystems": {  # Incorrect product value
            "is_intersystems": True,
            "running_instances": [{"instance_name": "IRIS1", "product": "x" * 100, "version": "2023.1"}],
        }
    },
    {
        "intersystems": {  # Incorrect version value
            "is_intersystems": True,
            "running_instances": [{"instance_name": "IRIS1", "product": "IRIS", "version": "2023-1-2"}],
        }
    },
    {
        "mssql": {  # Must be a string, not a number
            "version": 15.3,
        }
    },
    {
        "mssql": {  # Too long
            "version": "x" * 35,
        }
    },
    {"system_update_method": "inv_method"},
    {
        "conversions": {  # Must be a boolean, not a string
            "activity": "wrong"
        }
    },
    {
        "rhel_ai": {  # Must be a string, not a number
            "variant": "RHEL AI",
            "rhel_ai_version_id": 1.1,
            "amd_gpu_models": ["Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34"],
            "intel_gaudi_hpu_models": ["Habana Labs Ltd. Device 1020"],
            "nvidia_gpu_models": ["NVIDIA T1000", "Tesla V100-PCIE-16GB"],
        }
    },
    {
        "rhel_ai": {  # Must be a string as array elements, not a boolean
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.3",
            "amd_gpu_models": ["Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34"],
            "nvidia_gpu_models": [True, "Tesla V100-PCIE-16GB"],
        }
    },
    {
        "third_party_services": {
            "crowdstrike": {  # Too long falcon_aid
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8bx",
                "falcon_backend": "kernel",
                "falcon_version": "7.14.16703.0",
            }
        }
    },
    {
        "third_party_services": {
            "crowdstrike": {  # Must be a string, not a boolean
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": True,
            }
        }
    },
    {
        "third_party_services": {
            "crowdstrike": {  # Must be a string, not a boolean
                "falcon_version": True,
            }
        }
    },
    {
        "image_builder": {  # Must be a string
            "compliance_policy_id": 10,
            "compliance_profile_id": "some_profile_id",
        }
    },
    {
        "image_builder": {  # Must be a uuid
            "compliance_policy_id": "definitely not a uuid",
            "compliance_profile_id": "some_profile_id",
        }
    },
    {
        "image_builder": {  # Must be a string
            "compliance_policy_id": "b27443a3-078d-4ac2-bb46-ba7a8c31d21b",
            "compliance_profile_id": 10,
        }
    },
    {
        "workloads": {
            "ansible": {  # wrong data type for controller_version
                "controller_version": 1.0,
                "hub_version": "3.4.1",
                "catalog_worker_version": "100.387.9846.12",
                "sso_version": "1.28.3.52641.10000513168495123",
            }
        }
    },
    {
        "workloads": {
            "ansible": {  # sso_version too long
                "controller_version": "1.0",
                "hub_version": "3.4.1",
                "catalog_worker_version": "100.387.9846.12",
                "sso_version": "1.4" * 11,
            }
        }
    },
    {
        "workloads": {
            "ansible": {  # don't send "existence" booleans in place of versions
                "controller_version": True,
                "hub_version": False,
                "catalog_worker_version": False,
                "sso_version": False,
            }
        }
    },
    {
        "workloads": {
            "crowdstrike": {  # Too long falcon_aid
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8bx",
                "falcon_backend": "kernel",
                "falcon_version": "7.14.16703.0",
            }
        }
    },
    {
        "workloads": {
            "crowdstrike": {  # Must be a string, not a boolean
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": True,
            }
        }
    },
    {
        "workloads": {
            "crowdstrike": {  # Must be a string, not a boolean
                "falcon_version": True,
            }
        }
    },
    {
        "workloads": {
            "ibm_db2": {  # Must be a boolean, not a string
                "is_running": "yes",
            }
        }
    },
    {
        "workloads": {
            "intersystems": {  # Incorrect is_intersystems value
                "is_intersystems": "x",
                "running_instances": [{"instance_name": "IRIS1", "product": "IRIS", "version": "2023.1"}],
            }
        }
    },
    {
        "workloads": {
            "intersystems": {  # Incorrect instance_name value
                "is_intersystems": True,
                "running_instances": [{"instance_name": "x" * 300, "product": "IRIS", "version": "2023.1"}],
            }
        }
    },
    {
        "workloads": {
            "intersystems": {  # Incorrect product value
                "is_intersystems": True,
                "running_instances": [{"instance_name": "IRIS1", "product": "x" * 100, "version": "2023.1"}],
            }
        }
    },
    {
        "workloads": {
            "intersystems": {  # Incorrect version value
                "is_intersystems": True,
                "running_instances": [{"instance_name": "IRIS1", "product": "IRIS", "version": "2023-1-2"}],
            }
        }
    },
    {
        "workloads": {
            "mssql": {  # Must be a string, not a number
                "version": 15.3,
            }
        }
    },
    {
        "workloads": {
            "mssql": {  # Too long
                "version": "x" * 35,
            }
        }
    },
    {
        "workloads": {
            "oracle_db": {  # Must be a boolean, not a string
                "is_running": "yes",
            }
        }
    },
    {
        "workloads": {
            "rhel_ai": {  # Must be a string, not a number
                "variant": "RHEL AI",
                "rhel_ai_version_id": 1.1,
                "gpu_models": [
                    {"name": "NVIDIA L4", "vendor": "Nvidia", "memory": "24GB", "count": "2"},
                    {"name": "Tesla V100-PCIE-16GB", "vendor": "Nvidia", "memory": "16GB", "count": 4},
                ],
                "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
                "free_disk_storage": "698GB",
            }
        }
    },
    {
        "workloads": {
            "rhel_ai": {  # Must be a string as array elements, not a boolean
                "variant": "RHEL AI",
                "rhel_ai_version_id": "v1.1.3",
                "gpu_models": [
                    {"name": "NVIDIA L4", "vendor": "Nvidia", "memory": "24GB", "count": 2},
                    {"name": "Tesla V100-PCIE-16GB", "vendor": "Nvidia", "memory": "16GB", "count": 4},
                ],
                "ai_models": [True, "granite-7b-starter"],
                "free_disk_storage": "698GB",
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect version, too long
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.147857563665464",
                "sids": ["H2O"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect version, invalid symbols
                "sap_system": True,
                "instance_number": "03",
                "version": "1-00v122=04a1478575636",
                "sids": ["H2O"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect instance_number value
                "sap_system": True,
                "instance_number": "300",
                "version": "1.00.122.04.1478575636",
                "sids": ["H2O"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect sap_system value
                "sap_system": "x",
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["H2O"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect sids value
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["XXXX"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect sids value
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["XX"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect sids value
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["123"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect sids value
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["abc"],
            }
        }
    },
    {
        "workloads": {
            "sap": {  # Incorrect sids value
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["ABC", "ABC"],
            }
        }
    },
)


VALID_SYSTEM_PROFILES = (
    {"infrastructure_type": "x" * 100},
    {"infrastructure_vendor": "x" * 100},
    {"network_interfaces": [{"mac_address": "BD0DC5FB4235"}]},
    {"network_interfaces": [{"mac_address": "d3a94b06bbdd"}]},
    {"network_interfaces": [{"mac_address": "99:40:16:A9:38:21"}]},
    {"network_interfaces": [{"mac_address": "2f:3c:00:53:8c:71"}]},
    {"network_interfaces": [{"mac_address": "58-CA-D4-5F-D6-BE"}]},
    {"network_interfaces": [{"mac_address": "d5-90-c8-e0-3b-e5"}]},
    {"network_interfaces": [{"mac_address": "1EDC.C1E7.32BA"}]},
    {"network_interfaces": [{"mac_address": "a2da.8b79.40e0"}]},
    {"network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33"}]},
    {"network_interfaces": [{"mac_address": "00112233445566778899aabbccddeeff00112233"}]},
    {"network_interfaces": [{"name": "x" * 50}]},
    {"network_interfaces": [{"state": "x" * 25}]},
    {"network_interfaces": [{"type": "x" * 18}]},
    {"disk_devices": [{"device": "x" * 2048}]},
    {"disk_devices": [{"label": "x" * 1024}]},
    {"disk_devices": [{"options": {"something": "XXX"}}]},
    {"disk_devices": [{"mount_point": "x" * 2048}]},
    {"disk_devices": [{"type": "x" * 256}]},
    {"bios_vendor": "x" * 100},
    {"bios_version": "x" * 100},
    {"bios_release_date": "x" * 50},
    {"cpu_flags": ["x" * 30]},
    {"os_release": "x" * 100},
    {"os_kernel_version": "3.10.0"},
    {"releasever": "x" * 100},
    {"arch": "x" * 50},
    {"basearch": "x" * 50},
    {"kernel_modules": ["x" * 255]},
    {"last_boot_time": "2017-07-21T17:32:28Z"},
    {"running_processes": ["x" * 1000]},
    {"subscription_status": "x" * 100},
    {"subscription_auto_attach": "x" * 100},
    {"cloud_provider": "x" * 100},
    {"public_ipv4_addresses": ["123.123.123.123"]},
    {"public_dns": ["x" * 100]},
    {"yum_repos": [{"id": "x" * 256}]},
    {"yum_repos": [{"name": "x" * 1024}]},
    {"yum_repos": [{"base_url": "x" * 2048}]},
    {"dnf_modules": [{"name": "x" * 128}]},
    {"dnf_modules": [{"stream": "x" * 2048}]},
    {"dnf_modules": [{"name": "x", "stream": "y", "status": ["enabled"]}]},
    {"installed_products": [{"name": "x" * 512}]},
    {"installed_products": [{"id": "x" * 64}]},
    {"installed_products": [{"status": "x" * 256}]},
    {"insights_client_version": "x" * 50},
    {"insights_egg_version": "x" * 50},
    {"captured_date": "2017-07-21T17:32:28Z"},
    {"installed_packages": ["x" * 512]},
    {"gpg_pubkeys": ["x" * 512]},
    {"installed_services": ["x" * 512]},
    {"enabled_services": ["x" * 512]},
    {
        "sap": {
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
            "sids": ["H2O", "ABC", "C12"],
        }
    },
    {"sap_sids": ["H2O"]},
    {"sap_sids": ["ABC"]},
    {"sap_sids": ["C12"]},
    {"sap_system": True},
    {"sap_instance_number": "03"},
    {"sap_version": "1.00.122.04.1478575636"},
    {"tuned_profile": "x" * 256},
    {"selinux_current_mode": "enforcing"},
    {"selinux_config_file": "permissive"},
    {"owner_id": "22cd8e39-13bb-4d02-8316-84b850dc5136"},
    {"rhc_client_id": "22cd8e39-13bb-4d02-8316-84b850dc5136"},
    {"rhc_config_state": "22cd8e39-13bb-4d02-8316-84b850dc5136"},
    {"cpu_model": "Intel(R) Xeon(R) CPU E5-2690 0 @ 2.90GHz"},
    {"number_of_cpus": 35465},
    {"number_of_sockets": 35465},
    {"cores_per_socket": 35465},
    {"system_memory_bytes": 35465},
    {"network_interfaces": [{"ipv4_addresses": ["192.0.2.146"]}]},
    {"network_interfaces": [{"ipv6_addresses": ["0123:4567:89ab:cdef:0123:4567:89ab:cdef"]}]},
    {"network_interfaces": [{"mtu": 15}]},
    {"rhsm": {"version": "99Server"}},
    {"rhsm": {"environment_ids": ["46b6e690cc6a4906a3c9af4bca6e507d"]}},
    {"rhsm": {"environment_ids": ["I'm an opaque token. I can be any string."]}},
    {"operating_system": {"name": "RHEL", "major": 8, "minor": 10}},
    {"operating_system": {"name": "CentOS", "major": 7, "minor": 0}},
    {"operating_system": {"name": "CentOS Linux", "major": 7, "minor": 0}},
    {"katello_agent_running": False},
    {"satellite_managed": True},
    {"is_marketplace": True},
    {"yum_repos": [{"gpgcheck": True}]},
    {"yum_repos": [{"enabled": False}]},
    {
        "yum_repos": [
            {
                "mirrorlist": "https://rhui.redhat.com/pulp/mirror/content/dist/rhel8/rhui/$releasever/$basearch/baseos/os"
            }
        ]
    },
    {"installed_packages_delta": ["x" * 512]},
    {"host_type": "edge"},
    {"greenboot_status": "red"},
    {"greenboot_status": "green"},
    {"greenboot_fallback_detected": True},
    {"greenboot_fallback_detected": False},
    {
        "rpm_ostree_deployments": [
            {  # fully populated
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # version missing
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "fedora/33/x86_64/silverblue",
                "osname": "fedora-silverblue",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "rpm_ostree_deployments": [
            {  # origin empty
                "id": "fedora-silverblue-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
                "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
                "origin": "",
                "osname": "fedora-silverblue",
                "version": "33.21",
                "booted": True,
                "pinned": False,
            }
        ]
    },
    {
        "bootc_status": {
            "booted": {
                "image": "192.168.124.1:5000/bootc-insights:latest",
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",
                "cached_image": "192.168.124.1:5000/bootc-insights:latest",
                "cached_image_digest": "sha256:654275229d342b2836dcb8e5b851bbb1461b664a9fb9b8c934011e1abf15d778",
            },
            "rollback": {
                "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
                "image_digest": "sha256:92e476435ced1c148350c660b09c744717defbd300a15d33deda5b50ad6b21a0",
            },
        }
    },
    {
        "bootc_status": {
            "booted": {
                "image": "192.168.124.1:5000/bootc-insights:latest",
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",
                "cached_image": "192.168.124.1:5000/bootc-insights:latest",
                "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",
            },
            "staged": {
                "image": "192.168.124.1:5000/bootc-insights:latest",
                "image_digest": "sha256:654275229d342b2836dcb8e5b851bbb1461b664a9fb9b8c934011e1abf15d778",
                "cached_image": "192.168.124.1:5000/bootc-insights:latest",
                "cached_image_digest": "sha256:654275229d342b2836dcb8e5b851bbb1461b664a9fb9b8c934011e1abf15d778",
            },
        }
    },
    {
        "bootc_status": {
            "booted": {
                "image": "192.168.124.1:5000/bootc-insights:latest",
                "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",
            }
        }
    },
    {"system_purpose": {"usage": "Production", "role": "Red Hat Enterprise Linux Server", "sla": "Premium"}},
    {
        "system_purpose": {
            "usage": "Development/Test",
            "role": "Red Hat Enterprise Linux Workstation",
            "sla": "Standard",
        }
    },
    {
        "system_purpose": {
            "usage": "Disaster Recovery",
            "role": "Red Hat Enterprise Linux Compute Node",
            "sla": "Self-Support",
        }
    },
    {
        "ansible": {
            "controller_version": "1.0",
            "hub_version": "3.4.1",
            "catalog_worker_version": "100.387.9846.12",
            "sso_version": "1.28.3.52641.10000513168495123",
        }
    },
    {
        "intersystems": {
            "is_intersystems": True,
            "running_instances": [{"instance_name": "IRIS", "product": "IRIS", "version": "2023.1"}],
        }
    },
    {
        "mssql": {
            "version": "15.3",
        }
    },
    {"system_update_method": "yum"},
    {"conversions": {"activity": True}},
    {
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.3",
            "amd_gpu_models": [
                "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
                "Advanced Micro Devices, Inc. [AMD/ATI] Radeon PRO V320",
            ],
            "intel_gaudi_hpu_models": [
                "Habana Labs Ltd. Device 1020",
                "Habana Labs Ltd. HL-2000 AI Training Accelerator [Gaudi]",
            ],
            "nvidia_gpu_models": ["NVIDIA T1000", "Tesla V100-PCIE-16GB"],
        }
    },
    {
        "third_party_services": {
            "crowdstrike": {
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": "kernel",
                "falcon_version": "7.14.16703.0",
            }
        }
    },
    {
        "image_builder": {
            "compliance_policy_id": "b27443a3-078d-4ac2-bb46-ba7a8c31d21b",
            "compliance_profile_id": "some_profile_id",
        }
    },
    {
        "workloads": {
            "ansible": {
                "controller_version": "1.0",
                "hub_version": "3.4.1",
                "catalog_worker_version": "100.387.9846.12",
                "sso_version": "1.28.3.52641.10000513168495123",
            },
            "crowdstrike": {
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": "kernel",
                "falcon_version": "7.14.16703.0",
            },
            "ibm_db2": {
                "is_running": True,
            },
            "intersystems": {
                "is_intersystems": True,
                "running_instances": [{"instance_name": "IRIS", "product": "IRIS", "version": "2023.1"}],
            },
            "mssql": {
                "version": "15.3",
            },
            "oracle_db": {
                "is_running": True,
            },
            "rhel_ai": {
                "variant": "RHEL AI",
                "rhel_ai_version_id": "v1.1.3",
                "gpu_models": [
                    {"name": "NVIDIA L4", "vendor": "Nvidia", "memory": "24GB", "count": 2},
                    {"name": "Tesla V100-PCIE-16GB", "vendor": "Nvidia", "memory": "16GB", "count": 4},
                ],
                "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
                "free_disk_storage": "698GB",
            },
            "sap": {
                "sap_system": True,
                "instance_number": "03",
                "version": "1.00.122.04.1478575636",
                "sids": ["H2O", "ABC", "C12"],
            },
        }
    },
)
