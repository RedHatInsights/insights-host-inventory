from pytest import mark

from tests.helpers.db_utils import assert_host_exists_in_db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import generate_uuid


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
