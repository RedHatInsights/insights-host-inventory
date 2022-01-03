from contextlib import contextmanager
from copy import deepcopy
from os.path import join
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from yaml import safe_dump
from yaml import safe_load

from app.models import HostSchema
from app.models import LimitedHostSchema
from app.models import SPECIFICATION_DIR
from app.models import SYSTEM_PROFILE_SPECIFICATION_FILE


INVALID_SYSTEM_PROFILES = (
    {"infrastructure_type": "x" * 101},
    {"infrastructure_vendor": "x" * 101},
    {"network_interfaces": [{"mac_address": "x" * 60}]},
    {"network_interfaces": [{"name": "x" * 51}]},
    {"network_interfaces": [{"state": "x" * 26}]},
    {"network_interfaces": [{"type": "x" * 19}]},
    {"disk_devices": [{"device": "x" * 2049}]},
    {"disk_devices": [{"label": "x" * 1025}]},
    {"disk_devices": [{"mount_point": "x" * 2049}]},
    {"disk_devices": [{"type": "x" * 257}]},
    {"bios_vendor": "x" * 101},
    {"bios_version": "x" * 101},
    {"bios_release_date": "x" * 51},
    {"cpu_flags": ["x" * 31]},
    {"os_release": "x" * 101},
    {"os_kernel_version": "x" * 21},
    {"arch": "x" * 51},
    {"kernel_modules": ["x" * 256]},
    {"last_boot_time": "x" * 51},
    {"running_processes": ["x" * 1001]},
    {"subscription_status": ["x" * 101]},
    {"subscription_auto_attach": ["x" * 101]},
    {"cloud_provider": ["x" * 101]},
    {"yum_repos": [{"id": "x" * 257}]},
    {"yum_repos": [{"name": "x" * 1025}]},
    {"yum_repos": [{"base_url": "x" * 2049}]},
    {"dnf_modules": [{"name": "x" * 129}]},
    {"dnf_modules": [{"stream": "x" * 2049}]},
    {"installed_products": [{"name": "x" * 513}]},
    {"installed_products": [{"id": "x" * 65}]},
    {"installed_products": [{"status": "x" * 257}]},
    {"insights_client_version": "x" * 51},
    {"insights_egg_version": "x" * 51},
    {"captured_date": "x" * 33},
    {"installed_packages": ["x" * 513]},
    {"gpg_pubkeys": ["x" * 513]},
    {"installed_services": ["x" * 513]},
    {"enabled_services": ["x" * 513]},
    {"sap_sids": ["XXXX"]},
    {"sap_sids": ["XX"]},
    {"sap_sids": ["123"]},
    {"sap_sids": ["abc"]},
    {"sap_sids": ["ABC", "ABC"]},
    {"cpu_model": "x" * 101},
    {"rhc_client_id": "x" * 12},
    {"rhc_client_id": "plxi13y1-99ut-3rdf-bc10-84opf904lfad"},
)

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
            with patch("app.models.SYSTEM_PROFILE_SPECIFICATION_FILE", temp_file.name):
                yield
    finally:
        clear_schema_cache()
