import uuid

import pytest
from marshmallow import ValidationError as MarshmallowValidationError

from app.exceptions import ValidationException
from app.models import MAX_CANONICAL_FACTS_VERSION
from app.models import MIN_CANONICAL_FACTS_VERSION
from app.models import CanonicalFactsSchema
from app.models import Host
from app.models import db
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_uuid


def test_canonical_facts_version_default():
    canonical_facts = {"insights_id": generate_uuid()}
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["canonical_facts_version"] == MIN_CANONICAL_FACTS_VERSION


def test_canonical_facts_version_min():
    canonical_facts = {"canonical_facts_version": MIN_CANONICAL_FACTS_VERSION, "insights_id": generate_uuid()}
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["canonical_facts_version"] == MIN_CANONICAL_FACTS_VERSION


def test_canonical_facts_version_max():
    canonical_facts = {
        "canonical_facts_version": MAX_CANONICAL_FACTS_VERSION,
        "is_virtual": False,
        "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
        "insights_id": generate_uuid(),
    }
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["canonical_facts_version"] == MAX_CANONICAL_FACTS_VERSION


def test_canonical_facts_version_toolow():
    canonical_facts = {"canonical_facts_version": MIN_CANONICAL_FACTS_VERSION - 1, "insights_id": generate_uuid()}

    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_version_toohigh():
    canonical_facts = {"canonical_facts_version": MAX_CANONICAL_FACTS_VERSION + 1, "insights_id": generate_uuid()}

    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_v1_is_virtual_required():
    canonical_facts = {"canonical_facts_version": 1, "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"]}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize("is_virtual", (None, "", "XXX", 1))
def test_canonical_facts_v1_is_virtual_badvalues(is_virtual):
    canonical_facts = {
        "canonical_facts_version": 1,
        "is_virtual": is_virtual,
        "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
    }
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "ibm",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": "True",
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "ibm",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": "False",
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
        },
    ),
)
def test_canonical_facts_v1_is_virtual_goodvalues(canonical_facts):
    validated_host = CanonicalFactsSchema().load(canonical_facts)
    assert validated_host["is_virtual"] is True or validated_host["is_virtual"] is False


def test_canonical_facts_v1_mac_addresses_required():
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": False}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize("mac_addresses", ([], (), "c2:00:d0:c8:61:01", ["XXX"]))
def test_canonical_facts_v1_mac_addresses_badvalues(mac_addresses):
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": False, "mac_addresses": mac_addresses}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize("mac_addresses", (["c2:00:d0:c8:61:01"], ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"]))
def test_canonical_facts_v1_mac_addresses_goodvalues(mac_addresses):
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": False, "mac_addresses": mac_addresses}
    CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_v1_provider_required_for_virtual():
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": True, "mac_addresses": ["c2:00:d0:c8:61:01"]}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_v1_noprovider_when_notvirtual():
    canonical_facts = {
        "canonical_facts_version": 1,
        "is_virtual": False,
        "mac_addresses": ["c2:00:d0:c8:61:01"],
        "provider_type": "ibm",
        "provider_id": generate_uuid(),
    }
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_create_host_with_canonical_facts(db_create_host, db_get_host):
    host_data = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": "test.fqdn",
        "bios_uuid": generate_uuid(),
        "ip_addresses": ["192.168.1.1"],
        "mac_addresses": ["00:00:00:00:00:00"],
        "provider_id": "test_provider",
        "provider_type": "test_provider_type",
    }

    created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host.insights_id == uuid.UUID(host_data["insights_id"])
    assert retrieved_host.subscription_manager_id == host_data["subscription_manager_id"]
    assert retrieved_host.satellite_id == host_data["satellite_id"]
    assert retrieved_host.fqdn == host_data["fqdn"]
    assert retrieved_host.bios_uuid == host_data["bios_uuid"]
    assert retrieved_host.ip_addresses == host_data["ip_addresses"]
    assert retrieved_host.mac_addresses == host_data["mac_addresses"]
    assert retrieved_host.provider_id == host_data["provider_id"]
    assert retrieved_host.provider_type == host_data["provider_type"]


def test_create_host_with_missing_canonical_facts(db_create_host, db_get_host):
    host_data = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": "test.fqdn",
        "bios_uuid": generate_uuid(),
        "provider_id": "test_provider",
        "provider_type": "test_provider_type",
    }

    created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host.insights_id == uuid.UUID(host_data["insights_id"])
    assert retrieved_host.subscription_manager_id == host_data["subscription_manager_id"]
    assert retrieved_host.satellite_id == host_data["satellite_id"]
    assert retrieved_host.fqdn == host_data["fqdn"]
    assert retrieved_host.bios_uuid == host_data["bios_uuid"]
    assert retrieved_host.provider_id == host_data["provider_id"]
    assert retrieved_host.provider_type == host_data["provider_type"]
    assert retrieved_host.ip_addresses is None
    assert retrieved_host.mac_addresses is None


def test_update_canonical_facts_columns_uuid_comparison(db_create_host):
    """
    Test that updating a host with the same insights_id value doesn't incorrectly
    flag the field as modified when comparing UUID object with string.

    This test verifies the fix for a bug where update_canonical_facts_columns
    was comparing a UUID object (from database) with a string (from input),
    causing false positive change detection.
    """
    from sqlalchemy import inspect

    # Create a host with an insights_id
    insights_id_str = "8db0ffb4-ed3c-4376-968f-e4fdc734f193"
    host = db_create_host(extra_data={"insights_id": insights_id_str, "display_name": "test-host"})

    # Commit to ensure the host is fully persisted
    db.session.commit()

    # Verify the insights_id is stored correctly
    assert str(host.insights_id) == insights_id_str

    # Get the inspection before update
    _ = inspect(host)

    # Update with the same canonical facts (insights_id as string)
    # This should NOT mark insights_id as modified
    host.update(base_host(insights_id=insights_id_str, tags={}))

    # Get the inspection after update
    inspected_after = inspect(host)

    # Verify that insights_id was NOT marked as modified
    history = inspected_after.attrs.insights_id.history
    assert not history.has_changes(), "insights_id should not be marked as changed when value is the same"

    # Verify the value is still the same
    assert str(host.insights_id) == insights_id_str


@pytest.mark.parametrize(
    "field_name,uuid_value",
    [
        ("subscription_manager_id", generate_uuid()),
        ("bios_uuid", generate_uuid()),
        ("satellite_id", generate_uuid()),
    ],
)
def test_update_canonical_facts_columns_string_uuid_comparison(db_create_host, field_name, uuid_value):
    """
    Test that updating a host with the same string UUID canonical fact value doesn't incorrectly
    flag the field as modified when comparing string values.

    This test verifies that canonical facts fields stored as strings (but validated as UUIDs)
    are correctly compared and don't trigger false positive change detection.
    """
    from sqlalchemy import inspect

    # Create a host with the string UUID field
    extra_data = {field_name: uuid_value, "display_name": "test-host"}
    host = db_create_host(extra_data=extra_data)

    # Commit to ensure the host is fully persisted
    db.session.commit()

    # Verify the UUID field is stored correctly
    field_value = getattr(host, field_name)
    assert field_value == uuid_value

    # Get the inspection before update
    _ = inspect(host)

    # Update with the same canonical facts (UUID as string)
    # This should NOT mark the field as modified
    update_data = {field_name: uuid_value, "tags": {}}
    host.update(base_host(**update_data))

    # Get the inspection after update
    inspected_after = inspect(host)

    # Verify that the UUID field was NOT marked as modified
    history = inspected_after.attrs[field_name].history
    assert not history.has_changes(), f"{field_name} should not be marked as changed when value is the same"

    # Verify the value is still the same
    field_value_after = getattr(host, field_name)
    assert field_value_after == uuid_value


def test_host_init_raises_when_no_canonical_facts():
    """
    Host.__init__ must validate that at least one canonical fact field is present.
    """
    with pytest.raises(ValidationException, match="At least one of the canonical fact fields must be present"):
        # No canonical facts and no ID facts provided
        Host(
            account=USER_IDENTITY["account_number"],
            org_id=USER_IDENTITY["org_id"],
            reporter="test",
        )


def test_host_init_raises_when_only_non_id_canonical_facts():
    """
    Host.__init__ must validate that at least one ID fact is present, even if
    non-ID canonical facts are provided.
    """
    with pytest.raises(ValidationException, match="At least one of the ID fact fields must be present"):
        # Only non-ID canonical facts (e.g. fqdn) should raise the ID-fact validation error
        Host(
            account=USER_IDENTITY["account_number"],
            org_id=USER_IDENTITY["org_id"],
            reporter="test",
            fqdn="only-fqdn.example.com",
        )
