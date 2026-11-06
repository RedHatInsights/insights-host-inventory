from datetime import UTC
from datetime import datetime

import pytest
from marshmallow import ValidationError as MarshmallowValidationError

from app.models import ZERO_MAC_ADDRESS
from app.models import CanonicalFactsSchema
from app.models import HostAppDataAdvisor
from app.models import HostAppDataPatch
from app.models import HostAppDataVulnerability
from app.models import db
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_sample_profile_data
from tests.helpers.test_utils import now


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {"provider_type": "alibaba", "provider_id": generate_uuid()},
        {"provider_type": "aws", "provider_id": "i-05d2313e6b9a42b16"},
        {"provider_type": "azure", "provider_id": generate_uuid()},
        {"provider_type": "discovery", "provider_id": generate_uuid()},
        {"provider_type": "gcp", "provider_id": generate_uuid()},
        {"provider_type": "ibm", "provider_id": generate_uuid()},
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "alibaba",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": "i-05d2313e6b9a42b16",
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "azure",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "discovery",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "gcp",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "ibm",
            "provider_id": generate_uuid(),
        },
    ),
)
def test_valid_providers(canonical_facts):
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["provider_id"] == canonical_facts.get("provider_id")
    assert validated_host["provider_type"] == canonical_facts.get("provider_type")


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {
            "provider_type": "invalid",
            "provider_id": "i-05d2313e6b9a42b16",
        },  # invalid provider_type (value not in enum)
        {"provider_id": generate_uuid()},  # missing provider_type
        {"provider_type": "azure"},  # missing provider_id
        {"provider_type": "aws", "provider_id": None},  # invalid provider_id (None)
        {"provider_type": None, "provider_id": generate_uuid()},  # invalid provider_type (None)
        {"provider_type": "azure", "provider_id": ""},  # invalid provider_id (empty string)
        {"provider_type": "aws", "provider_id": "  "},  # invalid provider_id (blank space)
        {"provider_type": "aws", "provider_id": "\t"},  # invalid provider_id (tab),
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "invalid",
            "provider_id": "i-05d2313e6b9a42b16",
        },  # invalid provider_type (value not in enum)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_id": generate_uuid(),
        },  # missing provider_type
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "azure",
        },  # missing provider_id
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": None,
        },  # invalid provider_id (None)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": None,
            "provider_id": generate_uuid(),
        },  # invalid provider_type (None)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "azure",
            "provider_id": "",
        },  # invalid provider_id (empty string)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": "  ",
        },  # invalid provider_id (blank space)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": "\t",
        },  # invalid provider_id (tab)
    ),
)
def test_invalid_providers(canonical_facts):
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {"ip_addresses": ["127.0.0.1"]},
        {"ip_addresses": ["1.2.3.4"]},
        {"ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888"]},
        {"ip_addresses": ["::"]},
        {"ip_addresses": ["2001:db8::"]},
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["127.0.0.1"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.3.4"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["::"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["2001:db8::"],
        },
    ),
)
def test_valid_ip_addresses(canonical_facts):
    CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {"ip_addresses": ["just_a_string"]},
        {"ip_addresses": ["1.2.3"]},
        {"ip_addresses": ["1.2.3.4.5"]},
        {"ip_addresses": ["1.2.256.0"]},
        {"ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888:9999"]},
        {"ip_addresses": ["1111:2222:3333:4444:5555:6666:7777:gb8"]},
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["just_a_string"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.3"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.3.4.5"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.256.0"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888:9999"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1111:2222:3333:4444:5555:6666:7777:gb8"],
        },
    ),
)
def test_invalid_ip_addresses(canonical_facts):
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 0,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 0,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_only_v0(canonical_facts):
    #
    # For version 0 canonical facts, the zero mac address should be filtered out.
    # If the list is then empty it should proceed as though mac_addresses weren't provided.
    #
    validated_host = CanonicalFactsSchema().load(canonical_facts)
    assert "mac_addresses" not in validated_host


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_only_v1(canonical_facts):
    #
    # For version 1 canonical facts, the zero mac address should be filtered out.
    # If the list is then empty it should fail as though it was an empty list.
    #
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 0,
            "mac_addresses": ["c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 0,
            "mac_addresses": [ZERO_MAC_ADDRESS, "c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, "c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_filtered(canonical_facts):
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    #
    # If the zero mac address isn't the only element in the list,
    # it should succeed but the zero mac addresses should be removed.
    #
    assert len(validated_host["mac_addresses"]) == 1
    assert "c2:00:d0:c8:61:01" in validated_host["mac_addresses"]


def test_add_dynamic_profile(db_create_host):
    """
    Tests adding a HostDynamicSystemProfile record using a sample data dictionary.
    """

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})
    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    assert retrieved is not None
    for key, value in dynamic_profile_data.items():
        # We return datetime objects from the database,
        # so we need to convert them to strings for comparison
        if isinstance(getattr(retrieved, key), datetime):
            assert getattr(retrieved, key).astimezone(UTC).isoformat() == value
        else:
            assert getattr(retrieved, key) == value


def test_delete_dynamic_profile(db_create_host):
    """
    Tests deleting a HostDynamicSystemProfile record from the database.
    """

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})
    profile = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    db.session.delete(profile)
    db.session.commit()

    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one_or_none()

    assert retrieved is None


def test_dynamic_profile_incorrect_type(flask_app):  # noqa: ARG001
    """
    Tests that validating HostDynamicSystemProfile with incorrect data types raises an exception.
    """
    from app.models.system_profile_transformer import validate_and_transform

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    system_profile_data["number_of_cpus"] = "not-a-number"
    with pytest.raises(MarshmallowValidationError):
        validate_and_transform("test-org-id", "test-host-id", system_profile_data)


def test_validate_and_transform_strips_legacy_workload_root_fields():
    """Legacy root-level workload fields are migrated to workloads.* then stripped."""
    from app.models.system_profile_transformer import strip_legacy_workload_root_fields
    from app.models.system_profile_transformer import validate_and_transform

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {
        **static_profile_data,
        **dynamic_profile_data,
        "ansible": {"controller_version": "1.0"},
        "sap_sids": ["ABC"],
        "workloads": {"ansible": {"controller_version": "1.0"}, "sap": {"sids": ["ABC"]}},
    }

    stripped = strip_legacy_workload_root_fields(system_profile_data.copy())
    assert "ansible" not in stripped
    assert "sap_sids" not in stripped
    assert "workloads" in stripped

    validated_static, validated_dynamic = validate_and_transform("test-org-id", "test-host-id", system_profile_data)
    assert validated_dynamic.get("workloads") == system_profile_data["workloads"]


def test_validate_and_transform_migrates_legacy_sap_system_to_workloads():
    """Legacy-only sap_system is stored under workloads.sap on ingest."""
    from app.models.system_profile_transformer import validate_and_transform

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data, "sap_system": True}

    _, validated_dynamic = validate_and_transform("test-org-id", "test-host-id", system_profile_data)

    assert validated_dynamic["workloads"]["sap"]["sap_system"] is True
    assert "sap_system" not in validated_dynamic


def test_multiple_app_data_records_same_host(db_create_host):
    """Test that a single host can have multiple app data records."""
    host = db_create_host()
    current_time = now()

    # Create records for different app data types
    advisor_data = HostAppDataAdvisor(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        recommendations=5,
        incidents=2,
        critical=3,
        important=2,
        moderate=0,
        low=0,
    )

    vuln_data = HostAppDataVulnerability(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        total_cves=150,
        critical_cves=5,
    )

    patch_data = HostAppDataPatch(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        advisories_rhsa_installable=25,
    )

    db.session.add_all([advisor_data, vuln_data, patch_data])
    db.session.commit()

    # Verify all records exist
    advisor_retrieved = db.session.query(HostAppDataAdvisor).filter_by(org_id=host.org_id, host_id=host.id).first()
    vuln_retrieved = db.session.query(HostAppDataVulnerability).filter_by(org_id=host.org_id, host_id=host.id).first()
    patch_retrieved = db.session.query(HostAppDataPatch).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert advisor_retrieved is not None
    assert vuln_retrieved is not None
    assert patch_retrieved is not None
    assert advisor_retrieved.recommendations == 5
    assert vuln_retrieved.total_cves == 150
    assert patch_retrieved.advisories_rhsa_installable == 25
