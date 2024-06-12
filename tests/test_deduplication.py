import pytest
from pytest import mark

from app.auth.identity import Identity
from app.exceptions import InventoryException
from app.models import ProviderType
from lib.host_repository import find_existing_host
from lib.host_repository import IMMUTABLE_CANONICAL_FACTS
from tests.helpers.db_utils import assert_host_exists_in_db
from tests.helpers.db_utils import assert_host_missing_from_db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_fact
from tests.helpers.test_utils import generate_fact_dict
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import SYSTEM_IDENTITY


def test_find_host_using_subset_canonical_fact_match(db_create_host):
    fqdn = "fred.flintstone.com"
    canonical_facts = {"fqdn": fqdn, "bios_uuid": generate_uuid()}

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    # Create the subset of canonical facts to search by
    subset_canonical_facts = {"fqdn": fqdn}

    assert_host_exists_in_db(created_host.id, subset_canonical_facts)


def test_find_host_using_superset_canonical_fact_match(db_create_host):
    canonical_facts = {"fqdn": "fred", "bios_uuid": generate_uuid()}

    # Create the superset of canonical facts to search by
    superset_canonical_facts = canonical_facts.copy()
    superset_canonical_facts["satellite_id"] = generate_uuid()

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)
    assert_host_exists_in_db(created_host.id, superset_canonical_facts)


def test_find_host_canonical_fact_subset_match_different_elevated_ids(db_create_host):
    base_canonical_facts = {"fqdn": "fred", "bios_uuid": generate_uuid()}

    created_host_canonical_facts = base_canonical_facts.copy()
    created_host_canonical_facts["insights_id"] = generate_uuid()

    # Create the subset of canonical facts to search by
    search_canonical_facts = {"fqdn": "fred"}
    search_canonical_facts["subscription_manager_id"] = generate_uuid()

    created_host = db_create_host(host=minimal_db_host(canonical_facts=created_host_canonical_facts))

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


def test_find_host_canonical_fact_superset_match_different_elevated_ids(db_create_host):
    base_canonical_facts = {"fqdn": "fred", "bios_uuid": generate_uuid()}

    created_host_canonical_facts = base_canonical_facts.copy()
    created_host_canonical_facts["insights_id"] = generate_uuid()

    # Create the superset of canonical facts to search by
    search_canonical_facts = base_canonical_facts.copy()
    search_canonical_facts["subscription_manager_id"] = generate_uuid()
    search_canonical_facts["satellite_id"] = generate_uuid()

    created_host = db_create_host(host=minimal_db_host(canonical_facts=created_host_canonical_facts))

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


def test_find_correct_host_when_similar_canonical_facts(db_create_host):
    cf1 = {"fqdn": "fred", "bios_uuid": generate_uuid(), "insights_id": generate_uuid()}
    cf2 = {"fqdn": "george", "bios_uuid": generate_uuid(), "insights_id": generate_uuid()}
    cf3 = {"fqdn": cf1["fqdn"], "bios_uuid": cf1["bios_uuid"], "insights_id": cf2["insights_id"]}

    db_create_host(host=minimal_db_host(canonical_facts=cf1))
    created_host_2 = db_create_host(host=minimal_db_host(canonical_facts=cf2))

    assert_host_exists_in_db(created_host_2.id, cf3)


def test_no_merge_when_no_match(mq_create_or_update_host):
    wrapper = base_host(fqdn="test_fqdn", insights_id=generate_uuid())
    first_host = mq_create_or_update_host(wrapper)

    second_host = mq_create_or_update_host(
        minimal_host(
            bios_uuid=generate_uuid(),
            satellite_id=generate_uuid(),
            ansible_host="testhost",
            display_name="testdisplayname",
        )
    )

    assert first_host.id != second_host.id


#
# When lower priority facts change, we still match on high priority facts.
#
@pytest.mark.parametrize(
    "high_prio_match, low_prio_change",
    (
        ("provider_id", "insights_id"),
        ("provider_id", "subscription_manager_id"),
        ("mac_addresses", "insights_id"),
        ("mac_addresses", "subscription_manager_id"),
    ),
)
def test_high_prio_match_low_prio_change(mq_create_or_update_host, high_prio_match, low_prio_change):
    base_canonical_facts = generate_fact_dict(high_prio_match)
    base_canonical_facts[low_prio_change] = generate_fact(low_prio_change)

    wrapper = base_host(**base_canonical_facts)
    first_host = mq_create_or_update_host(wrapper)

    base_canonical_facts[low_prio_change] = generate_fact(low_prio_change)

    wrapper = base_host(**base_canonical_facts)
    second_host = mq_create_or_update_host(wrapper)

    assert first_host.id == second_host.id


#
# When mutable high priority facts change, match on lower level facts.
# When immutable high priority facts are different, no match even when lower level facts match.
#
@pytest.mark.parametrize(
    "high_prio_change, low_prio_match",
    (
        ("provider_id", "insights_id"),
        ("provider_id", "subscription_manager_id"),
        ("mac_addresses", "insights_id"),
        ("mac_addresses", "subscription_manager_id"),
    ),
)
def test_high_prio_change_low_prio_match(mq_create_or_update_host, high_prio_change, low_prio_match):
    base_canonical_facts = generate_fact_dict(high_prio_change)
    base_canonical_facts[low_prio_match] = generate_fact(low_prio_match)

    wrapper = base_host(**base_canonical_facts)
    first_host = mq_create_or_update_host(wrapper)

    base_canonical_facts.update(generate_fact_dict(high_prio_change))

    wrapper = base_host(**base_canonical_facts)
    second_host = mq_create_or_update_host(wrapper)

    if high_prio_change in IMMUTABLE_CANONICAL_FACTS:
        # When an immutable fact is different, then it should never match.
        assert first_host.id != second_host.id
    else:
        assert first_host.id == second_host.id


#
# When a mutable canonical fact changes, and a higher priority fact is not set in the database
# but the higher priority fact is provided in the report, there should be no match.
#
@pytest.mark.parametrize(
    "high_prio_fact, low_prio_fact",
    (
        ("provider_id", "insights_id"),
        ("provider_id", "subscription_manager_id"),
        ("mac_addresses", "insights_id"),
        ("mac_addresses", "subscription_manager_id"),
    ),
)
def test_lowlevel_change_highlevel_notset_provided_nomatch(mq_create_or_update_host, high_prio_fact, low_prio_fact):
    base_canonical_facts = generate_fact_dict(low_prio_fact)

    wrapper = base_host(**base_canonical_facts)
    first_host = mq_create_or_update_host(wrapper)

    changed_canonical_facts = base_canonical_facts.copy()
    changed_canonical_facts[low_prio_fact] = generate_fact(low_prio_fact)
    changed_canonical_facts.update(generate_fact_dict(high_prio_fact))

    wrapper = base_host(**changed_canonical_facts)
    second_host = mq_create_or_update_host(wrapper)

    assert first_host.id != second_host.id


@mark.parametrize("changing_id", ("provider_id", "insights_id"))
def test_elevated_id_priority_order_nomatch(db_create_host, changing_id):
    base_canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }

    created_host_canonical_facts = base_canonical_facts.copy()
    created_host_canonical_facts.update(generate_fact_dict(changing_id))

    search_canonical_facts = base_canonical_facts.copy()
    search_canonical_facts.update(generate_fact_dict(changing_id))

    created_host = db_create_host(host=minimal_db_host(canonical_facts=created_host_canonical_facts))

    assert_host_exists_in_db(created_host.id, created_host_canonical_facts)
    if changing_id in IMMUTABLE_CANONICAL_FACTS:
        # When an immutable fact is different, then it should never match.
        assert_host_missing_from_db(search_canonical_facts)
    else:
        # When a mutable fact is different, we should still try to match
        # on lower-priority facts, assuming the mutable fact may have changed.
        # In this case, we failed to match on insights_id, but we did match
        # on subscription_manager_id. Here, it's reasonably safe to conclude
        # the insights_id has changed, and this is the host that needs to be updated.
        assert_host_exists_in_db(created_host.id, search_canonical_facts)


@mark.parametrize("changing_id", ("insights_id", "subscription_manager_id"))
def test_elevated_id_priority_order_match(db_create_host, changing_id):
    base_canonical_facts = {
        "provider_id": generate_uuid(),
        "provider_type": ProviderType.AWS,
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }

    created_host = db_create_host(host=minimal_db_host(canonical_facts=base_canonical_facts))

    match_host_canonical_facts = base_canonical_facts.copy()
    match_host_canonical_facts[changing_id] = generate_fact(changing_id)

    assert_host_exists_in_db(created_host.id, match_host_canonical_facts)


def test_no_merge_when_different_facts(db_create_host):
    cf1 = {"fqdn": "fred", "bios_uuid": generate_uuid(), "insights_id": generate_uuid()}
    cf2 = {"fqdn": "george", "bios_uuid": generate_uuid(), "subscription_manager_id": generate_uuid()}

    db_create_host(host=minimal_db_host(canonical_facts=cf1))

    assert_host_missing_from_db(cf2)


def test_find_host_using_insights_id_match(db_create_host):
    canonical_facts = {"fqdn": "fred", "bios_uuid": generate_uuid(), "insights_id": generate_uuid()}

    # Change the canonical facts except the insights_id...match on insights_id
    search_canonical_facts = {
        "fqdn": "barney",
        "bios_uuid": generate_uuid(),
        "insights_id": canonical_facts["insights_id"],
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


def test_find_host_using_subscription_manager_id_match(db_create_host):
    canonical_facts = {"fqdn": "fred", "bios_uuid": generate_uuid(), "subscription_manager_id": generate_uuid()}

    # Change the bios_uuid so that falling back to subset match will fail
    search_canonical_facts = {
        "bios_uuid": generate_uuid(),
        "subscription_manager_id": canonical_facts["subscription_manager_id"],
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


#
# This test reproduces the sequence of events that caused the creation
# of duplicate hosts with the same provider_id/provider_type.
# The test asserts that this sequence of events no longer results
# in the creation of such duplicates.
#
def test_provider_id_dup(mq_create_or_update_host, db_get_host):
    provider_id = generate_uuid()

    subscription_manager_id_x = generate_uuid()
    subscription_manager_id_y = generate_uuid()

    canonical_facts = {
        "subscription_manager_id": subscription_manager_id_x,
        "provider_id": provider_id,
        "provider_type": ProviderType.AWS,
    }
    first_host = minimal_host(**canonical_facts)
    del first_host.ip_addresses
    first_host.reporter = "rhsm-system-profile-bridge"
    created_first_host = mq_create_or_update_host(first_host)

    assert_host_exists_in_db(created_first_host.id, canonical_facts)
    assert created_first_host.provider_id == provider_id

    canonical_facts = {
        "subscription_manager_id": subscription_manager_id_y,
        "provider_id": provider_id,
        "provider_type": ProviderType.AWS,
    }
    second_host = minimal_host(**canonical_facts)
    del second_host.ip_addresses
    second_host.reporter = "cloud-connector"
    created_second_host = mq_create_or_update_host(second_host)

    assert_host_exists_in_db(created_second_host.id, canonical_facts)
    # Should have matched the first host.
    assert created_second_host.id == created_first_host.id
    assert created_second_host.provider_id == provider_id

    canonical_facts = {
        "subscription_manager_id": subscription_manager_id_y,
        "provider_id": provider_id,
        "provider_type": ProviderType.AWS,
    }
    third_host = minimal_host(**canonical_facts)
    del third_host.ip_addresses
    third_host.reporter = "rhsm-system-profile-bridge"
    created_third_host = mq_create_or_update_host(third_host)

    assert_host_exists_in_db(created_third_host.id, canonical_facts)
    assert created_third_host.id == created_first_host.id
    assert created_third_host.id == created_second_host.id


@mark.parametrize("changing_id", ("insights_id", "subscription_manager_id"))
def test_rhsm_conduit_elevated_id_priority_no_identity(mq_create_or_update_host, changing_id):
    base_canonical_facts = {
        "account": SYSTEM_IDENTITY["account_number"],
        "provider_type": ProviderType.AWS,
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }

    platform_metadata = {"request_id": "b9757340-f839-4541-9af6-f7535edf08db"}

    first_host = minimal_host(**base_canonical_facts)
    first_host.reporter = "rhsm-conduit"
    created_first_host = mq_create_or_update_host(first_host, platform_metadata=platform_metadata)

    second_host_canonical_facts = base_canonical_facts.copy()
    second_host_canonical_facts[changing_id] = generate_fact(changing_id)
    second_host = minimal_host(**second_host_canonical_facts)
    second_host.reporter = "rhsm-conduit"
    created_second_host = mq_create_or_update_host(second_host, platform_metadata=platform_metadata)

    assert created_first_host.id == created_second_host.id


def test_subscription_manager_id_case_insensitive(mq_create_or_update_host):
    smid = generate_uuid()

    first_host = mq_create_or_update_host(minimal_host(subscription_manager_id=smid.upper()))
    second_host = mq_create_or_update_host(minimal_host(subscription_manager_id=smid.lower()))
    assert first_host.id == second_host.id


def test_mac_addresses_case_insensitive(mq_create_or_update_host):
    first_host = mq_create_or_update_host(
        base_host(fqdn="foo.bar.com", mac_addresses=["C2:00:D0:C8:61:01", "aa:bb:cc:dd:ee:ff"])
    )
    second_host = mq_create_or_update_host(
        base_host(fqdn="foo.bar.com", mac_addresses=["c2:00:d0:c8:61:01", "AA:BB:CC:DD:EE:FF"])
    )
    assert first_host.id == second_host.id


def test_find_host_using_provider_id_and_type_match(db_create_host):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "provider_id": generate_uuid(),
        "provider_type": ProviderType.AWS,
    }

    search_canonical_facts = {
        "provider_id": canonical_facts["provider_id"],
        "provider_type": canonical_facts["provider_type"],
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


def test_find_host_using_provider_id_different_type_nomatch(db_create_host):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "provider_id": generate_uuid(),
        "provider_type": ProviderType.AWS,
    }

    search_canonical_facts = {
        "provider_id": canonical_facts["provider_id"],
        "provider_type": ProviderType.IBM,
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    db_create_host(host=host)

    assert_host_missing_from_db(search_canonical_facts)


def test_find_host_using_provider_id_no_type_exception(db_create_host):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "provider_id": generate_uuid(),
        "provider_type": ProviderType.AWS,
    }

    search_canonical_facts = {
        "provider_id": canonical_facts["provider_id"],
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    db_create_host(host=host)

    with pytest.raises(InventoryException):
        find_existing_host(Identity(SYSTEM_IDENTITY), search_canonical_facts)


def test_find_host_using_provider_id_existing_with_match(db_create_host):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "provider_id": generate_uuid(),
        "provider_type": ProviderType.AWS,
    }

    search_canonical_facts = {
        "insights_id": canonical_facts["insights_id"],
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


def test_find_host_using_provider_id_existing_without_match(db_create_host):
    canonical_facts = {"insights_id": generate_uuid()}

    search_canonical_facts = {
        "insights_id": canonical_facts["insights_id"],
        "provider_id": generate_uuid(),
        "provider_type": ProviderType.AWS,
    }

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    assert_host_exists_in_db(created_host.id, search_canonical_facts)


def test_find_correct_host_varying_provider_type(db_create_host, mq_create_or_update_host):
    provider_id = generate_uuid()  # common provider_id
    aws_canonical_facts = {"provider_id": provider_id, "provider_type": ProviderType.AWS}
    ibm_canonical_facts = {"provider_id": provider_id, "provider_type": ProviderType.IBM}

    aws_host = db_create_host(host=minimal_db_host(canonical_facts=aws_canonical_facts))
    aws_host_id = aws_host.id
    assert_host_exists_in_db(aws_host_id, aws_canonical_facts)

    ibm_host = db_create_host(host=minimal_db_host(canonical_facts=ibm_canonical_facts))
    ibm_host_id = ibm_host.id
    assert_host_exists_in_db(ibm_host_id, ibm_canonical_facts)

    aws_found_host = mq_create_or_update_host(minimal_host(**aws_canonical_facts))
    assert aws_found_host.id == str(aws_host_id)

    ibm_found_host = mq_create_or_update_host(minimal_host(**ibm_canonical_facts))
    assert ibm_found_host.id == str(ibm_host_id)

    assert aws_found_host.id != ibm_found_host.id
