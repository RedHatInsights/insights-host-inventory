"""Small, deterministic system profile datasets shared by the profile filter and projection tests."""

from datetime import datetime
from datetime import timedelta
from types import SimpleNamespace

from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.test_utils import get_sample_dynamic_profile_data
from tests.helpers.test_utils import get_sample_static_profile_data

UUID_VALUES = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
)
DATE_VALUES = ("2024-01-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00")
STRING_FIELDS = (
    "cpu_model",
    "infrastructure_type",
    "infrastructure_vendor",
    "bios_vendor",
    "bios_version",
    "bios_release_date",
    "os_release",
    "arch",
    "basearch",
    "releasever",
    "subscription_status",
    "subscription_auto_attach",
    "cloud_provider",
    "insights_client_version",
    "insights_egg_version",
    "tuned_profile",
    "selinux_config_file",
)
UUID_FIELDS = ("owner_id", "rhc_client_id", "rhc_config_state", "virtual_host_uuid")
DATE_FIELDS = ("last_boot_time", "captured_date")
ENUM_VALUES = {
    "selinux_current_mode": ("enforcing", "permissive"),
    "host_type": ("edge", "edge"),
    "greenboot_status": ("red", "green"),
    "system_update_method": ("dnf", "rpm-ostree"),
}
INTEGER_FIELDS = ("number_of_cpus", "number_of_sockets", "cores_per_socket", "threads_per_core", "system_memory_bytes")
BOOLEAN_FIELDS = (
    "katello_agent_running",
    "satellite_managed",
    "sap_system",
    "is_marketplace",
    "greenboot_fallback_detected",
)
BOOLEAN_INDICES = dict(zip(BOOLEAN_FIELDS, ((0, 1), (1, 0), (0, 2), (2, 0), (1, 2)), strict=True))
LEGACY_WORKLOAD_FIELDS = (
    "ansible",
    "crowdstrike",
    "ibm_db2",
    "intersystems",
    "mssql",
    "oracle_db",
    "rhel_ai",
    "sap",
    "sap_instance_number",
    "sap_sids",
    "sap_system",
    "sap_version",
    "third_party_services",
)
INVALID_COMPARATORS = (
    "not_eq",
    "not_eq_i",
    "contains",
    "contains_i",
    "starts_with",
    "starts_with_i",
    "ends_with",
    "ends_with_i",
    "unknownoperation",
)


def scalar_profiles():
    # Three ordered values, empty strings, and a completely missing profile.
    profiles = [{}, {}, {}, {}, {}]
    for field in STRING_FIELDS:
        for index, value in enumerate(("first / & +'value", "second-value", "third-value", "")):
            profiles[index][field] = f"{field}: {value}" if value else ""
    for field_index, field in enumerate(UUID_FIELDS):
        for index in range(3):
            profiles[index][field] = f"{field_index + index * 10 + 1:08x}-1111-4111-8111-111111111111"
    for field_index, field in enumerate(DATE_FIELDS):
        for index, value in enumerate(DATE_VALUES):
            profiles[index][field] = (datetime.fromisoformat(value) + timedelta(days=field_index)).isoformat()
    for field, values in ENUM_VALUES.items():
        for index, value in enumerate(values):
            profiles[index][field] = value
    for field_index, field in enumerate(INTEGER_FIELDS):
        for index, value in enumerate((10, 20, 30)):
            profiles[index][field] = (value + field_index * 100) * (2**32 if field == "system_memory_bytes" else 1)
    for field in BOOLEAN_FIELDS:
        for index, value in zip(BOOLEAN_INDICES[field], (True, False), strict=True):
            if field == "sap_system":
                profiles[index]["workloads"] = {"sap": {"sap_system": value}}
            else:
                profiles[index][field] = value
    return profiles


def create_profile_hosts(db_create_host, profiles, **extra_data):
    hosts = []
    for index, profile in enumerate(profiles):
        host = db_create_host(
            extra_data={
                **extra_data,
                "system_profile_facts": profile,
                "tags": [
                    {"namespace": "profile", "key": f"host-{index}-{suffix}", "value": "selected"}
                    for suffix in ("a", "b")
                ],
            }
        )
        # Requests close the scoped session; don't retain expired SQLAlchemy objects.
        hosts.append(SimpleNamespace(id=str(host.id), org_id=host.org_id))
    return hosts


def assert_profile_filter_results(api_get, query, hosts, expected_indices):
    """Assert host selection AND the tag aggregation wired to that selection."""
    expected_hosts = [hosts[index] for index in expected_indices]
    status, response = api_get(build_hosts_url(query=query))
    assert status == 200, response
    assert response["count"] == len(expected_hosts)
    assert {host["id"] for host in response["results"]} == {str(host.id) for host in expected_hosts}
    assert all(host["org_id"] == expected_hosts[0].org_id for host in response["results"])

    status, response = api_get(build_tags_url(query=query))
    assert status == 200, response
    expected_tags = {f"host-{index}-{suffix}" for index in expected_indices for suffix in ("a", "b")}
    assert response["count"] == len(expected_tags)
    assert {item["tag"]["key"] for item in response["results"]} == expected_tags
    for item in response["results"]:
        assert item["tag"]["namespace"] == "profile"
        assert item["tag"]["value"] == "selected"
        assert item["count"] == 1


def round_trip_profile():
    """Reuse local field data, replacing its illustrative, non-schema nested values."""
    static = get_sample_static_profile_data()
    for field in ("host_type", "bootc_status", "third_party_services"):
        static.pop(field)
    static.update(
        operating_system={"name": "RHEL", "major": 9, "minor": 3},
        conversions={"activity": True},
        image_builder={"blueprint_id": UUID_VALUES[0]},
    )
    static["rpm_ostree_deployments"][0].update(
        checksum="a" * 64, origin="rhel/9/x86_64/edge", booted=True, pinned=False
    )
    dynamic = get_sample_dynamic_profile_data()
    dynamic["systemd"] = {"failed": 1, "jobs_queued": 4, "state": "running", "failed_services": ["sshd"]}
    dynamic["workloads"]["intersystems"]["running_instances"] = [
        {"instance_name": "IRIS3", "product": "IRIS", "version": "2023.1"}
    ]
    return static, dynamic


def bootc_image(kind, index):
    return {
        "image": f"quay.io/{kind}-{index}:latest",
        "image_digest": "sha256:" + f"{ord(kind) * 100 + index:064x}",
        "cached_image": f"quay.io/{kind}c-{index}:latest",
        "cached_image_digest": "sha256:" + f"{ord(kind) * 100 + index + 10000:064x}",
    }


def bootc_profiles():
    profiles = [{} for _ in range(10)]
    for index, kinds in ((1, "b"), (2, "r"), (3, "s"), (4, "bs"), (5, "b"), (6, "b"), (7, "brs"), (8, "brs")):
        profiles[index]["bootc_status"] = {
            {"b": "booted", "r": "rollback", "s": "staged"}[kind]: bootc_image(kind, index) for kind in kinds
        }
    for field in ("cached_image", "cached_image_digest"):
        profiles[5]["bootc_status"]["booted"].pop(field)
    for field in ("image", "image_digest"):
        profiles[6]["bootc_status"]["booted"].pop(field)
    profiles[9]["host_type"] = "edge"
    return profiles
