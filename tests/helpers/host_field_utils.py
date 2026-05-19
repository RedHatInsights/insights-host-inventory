# mypy: disallow-untyped-defs

from __future__ import annotations

from tests.helpers.test_utils import generate_uuid

CANONICAL_FIELDS: set[str] = {
    "insights_id",
    "subscription_manager_id",
    "satellite_id",
    "bios_uuid",
    "ip_addresses",
    "fqdn",
    "mac_addresses",
    "provider_id",
    "provider_type",
}


VALID_HOST_FIELDS: tuple[dict, ...] = (
    # --- UUID fields ---
    {"insights_id": generate_uuid()},
    {"subscription_manager_id": generate_uuid()},
    {"bios_uuid": generate_uuid()},
    # --- satellite_id (UUID and 10+ digit numeric) ---
    {"satellite_id": generate_uuid()},
    {"satellite_id": "1234567890"},
    # --- String fields: boundary values ---
    {"fqdn": "a"},
    {"fqdn": "x" * 255, "display_name": "long-fqdn-host"},
    {"display_name": "h"},
    {"display_name": "x" * 200},
    {"ansible_host": ""},
    {"ansible_host": "x" * 255},
    {"account": ""},
    {"account": "1234567890"},
    # --- IP addresses ---
    {"ip_addresses": []},
    {"ip_addresses": ["192.168.1.1"]},
    {"ip_addresses": ["192.168.1.1", "10.0.0.1"]},
    {"ip_addresses": ["192.168.1.1", "2001:0db8:85a3:0000:0000:8a2e:0370:7334"]},
    {"ip_addresses": [f"10.0.0.{i}" for i in range(1, 11)]},
    # --- MAC addresses (various formats) ---
    {"mac_addresses": ["aa:bb:cc:dd:ee:ff"]},
    {"mac_addresses": ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"]},
    {"mac_addresses": ["58-CA-D4-5F-D6-BE"]},
    {"mac_addresses": ["aabbccddeeff"]},
    {"mac_addresses": ["1EDC.C1E7.32BA"]},
    {"mac_addresses": ["00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33"]},
    # --- Provider type + provider_id (compound) ---
    {"provider_type": "alibaba", "provider_id": generate_uuid()},
    {"provider_type": "aws", "provider_id": generate_uuid()},
    {"provider_type": "azure", "provider_id": generate_uuid()},
    {"provider_type": "discovery", "provider_id": generate_uuid()},
    {"provider_type": "gcp", "provider_id": generate_uuid()},
    {"provider_type": "ibm", "provider_id": generate_uuid()},
    {"provider_id": "x" * 500, "provider_type": "aws"},
    # --- Facts ---
    {"facts": [{"namespace": "ns1", "facts": {"key1": "value1"}}]},
    {"facts": [{"namespace": "ns1", "facts": {"k1": "v1"}}, {"namespace": "ns2", "facts": {"k2": "v2"}}]},
)


_VALID_UUID = generate_uuid()

INVALID_HOST_FIELDS: tuple[dict, ...] = (
    # --- Invalid UUID formats ---
    # insights_id entries include a valid subscription_manager_id so the host
    # always has a queryable ID for the "not persisted" assertion.
    {"insights_id": "not-a-uuid", "subscription_manager_id": generate_uuid()},
    {"insights_id": _VALID_UUID.replace("-", ""), "subscription_manager_id": generate_uuid()},
    {"insights_id": [_VALID_UUID], "subscription_manager_id": generate_uuid()},
    {"insights_id": _VALID_UUID[:23], "subscription_manager_id": generate_uuid()},
    {"insights_id": _VALID_UUID + "a", "subscription_manager_id": generate_uuid()},
    {"insights_id": "", "subscription_manager_id": generate_uuid()},
    {"subscription_manager_id": "bad-uuid"},
    {"subscription_manager_id": ""},
    {"bios_uuid": "bad-uuid"},
    {"bios_uuid": ""},
    # --- Invalid satellite_id ---
    {"satellite_id": "123456789"},
    {"satellite_id": ""},
    {"satellite_id": "abc!@#$%"},
    # --- String too long ---
    {"display_name": "x" * 201},
    {"fqdn": "x" * 256},
    {"ansible_host": "x" * 256},
    {"account": "x" * 11},
    {"org_id": "x" * 37},
    {"reporter": "x" * 256},
    # --- String too short (below min > 0) ---
    {"fqdn": ""},
    {"org_id": ""},
    {"reporter": ""},
    # --- Invalid IP addresses ---
    {"ip_addresses": "192.168.1.1"},
    {"ip_addresses": ["not-an-ip"]},
    {"ip_addresses": [None]},
    {"ip_addresses": [""]},
    {"ip_addresses": {}},
    {"ip_addresses": ["64.333.161.147"]},
    # --- Invalid MAC addresses ---
    {"mac_addresses": "aa:bb:cc:dd:ee:ff"},
    {"mac_addresses": ["bad"]},
    {"mac_addresses": [None]},
    {"mac_addresses": [""]},
    {"mac_addresses": ["Z1:Z2:Z3:Z4:Z5:Z6"]},
    {"mac_addresses": ["BD0DC5FB42356"]},
    {"mac_addresses": ["BD0DC5FB423"]},
    {"mac_addresses": ["BD:0D:C5:FB:42:35:66"]},
    {"mac_addresses": ["BD:0D:C5:FB:42:3"]},
    {"mac_addresses": ["1EDC.C1E7.32BA.ABCD"]},
    {"mac_addresses": ["1EDC.C1E7"]},
    # --- Invalid provider combos ---
    {"provider_type": "aws"},
    {"provider_id": generate_uuid(), "subscription_manager_id": generate_uuid()},
    {"provider_type": "invalid_provider", "provider_id": generate_uuid()},
    {"provider_type": "unknown", "provider_id": generate_uuid()},
    {"provider_type": "", "provider_id": generate_uuid()},
    {"provider_id": "   ", "provider_type": "aws"},
    # --- Null values (non-canonical fields) ---
    {"display_name": None},
    {"ansible_host": None},
    {"account": None},
    {"org_id": None},
    {"facts": None},
    {"tags": None},
    {"system_profile": None},
    {"reporter": None},
    {"stale_timestamp": None},
    # --- Invalid types ---
    {"display_name": ["list"]},
    {"display_name": {}},
    # --- Facts with empty JSON keys ---
    {"facts": [{"namespace": "rhsm", "facts": {"": "invalid"}}]},
    {"facts": [{"namespace": "rhsm", "facts": {"metadata": {"": "invalid"}}}]},
)
