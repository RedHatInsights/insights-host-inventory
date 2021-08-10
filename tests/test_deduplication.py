from pytest import mark

from tests.helpers.db_utils import assert_host_exists_in_db
from tests.helpers.db_utils import assert_host_missing_from_db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


def test_find_host_using_subset_canonical_fact_match(db_create_host):
    fqdn = "fred.flintstone.com"
    canonical_facts = {"fqdn": fqdn, "bios_uuid": generate_uuid(), "rhel_machine_id": generate_uuid()}

    host = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host)

    # Create the subset of canonical facts to search by
    subset_canonical_facts = {"fqdn": fqdn}

    assert_host_exists_in_db(created_host.id, subset_canonical_facts)


def test_find_host_using_superset_canonical_fact_match(db_create_host):
    canonical_facts = {"fqdn": "fred", "bios_uuid": generate_uuid()}

    # Create the superset of canonical facts to search by
    superset_canonical_facts = canonical_facts.copy()
    superset_canonical_facts["rhel_machine_id"] = generate_uuid()
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


def test_no_merge_when_no_match(mq_create_or_update_host):
    wrapper = minimal_host(fqdn="test_fqdn", insights_id=generate_uuid())
    del wrapper.ip_addresses
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


def test_subscription_manager_id_case_insensitive(mq_create_or_update_host):
    smid = generate_uuid()

    first_host = mq_create_or_update_host(minimal_host(subscription_manager_id=smid.upper()))
    second_host = mq_create_or_update_host(minimal_host(subscription_manager_id=smid.lower()))
    assert first_host.id == second_host.id


def test_mac_addresses_case_insensitive(mq_create_or_update_host):
    first_host = mq_create_or_update_host(
        minimal_host(fqdn="foo.bar.com", mac_addresses=["C2:00:D0:C8:61:01", "aa:bb:cc:dd:ee:ff"])
    )
    second_host = mq_create_or_update_host(
        minimal_host(fqdn="foo.bar.com", mac_addresses=["c2:00:d0:c8:61:01", "AA:BB:CC:DD:EE:FF"])
    )
    assert first_host.id == second_host.id


@mark.parametrize(("host_create_order", "expected_host"), (((0, 1), 1), ((1, 0), 0)))
def test_insights_id_is_preferred_over_subscription_manager_id(db_create_host, host_create_order, expected_host):
    multiple_hosts_canonical_facts = ({"subscription_manager_id": generate_uuid()}, {"insights_id": generate_uuid()})

    created_hosts = []
    for single_host_canonical_facts in host_create_order:
        host = minimal_db_host(canonical_facts=multiple_hosts_canonical_facts[single_host_canonical_facts])
        created_host = db_create_host(host=host)
        created_hosts.append(created_host)

    search_canonical_facts = {
        key: value
        for single_host_canonical_facts in multiple_hosts_canonical_facts
        for key, value in single_host_canonical_facts.items()
    }

    assert_host_exists_in_db(created_hosts[expected_host].id, search_canonical_facts)


@mark.parametrize(("host_create_order", "expected_host"), (((0, 1, 2), 2), ((2, 1, 0), 0), ((0, 2, 1), 1)))
def test_provider_id_preference_over_other_elevated_facts(db_create_host, host_create_order, expected_host):
    multiple_hosts_canonical_facts = (
        {"subscription_manager_id": generate_uuid()},
        {"insights_id": generate_uuid()},
        {"provider_type": "aws", "provider_id": "i-05d2313e6b9a42b16"},
    )

    created_hosts = []
    for single_host_canonical_facts in host_create_order:
        host = minimal_db_host(canonical_facts=multiple_hosts_canonical_facts[single_host_canonical_facts])
        created_host = db_create_host(host=host)
        created_hosts.append(created_host)

    search_canonical_facts = {
        key: value
        for single_host_canonical_facts in multiple_hosts_canonical_facts
        for key, value in single_host_canonical_facts.items()
    }

    assert_host_exists_in_db(created_hosts[expected_host].id, search_canonical_facts)
