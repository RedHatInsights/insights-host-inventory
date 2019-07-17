import uuid

from pytest import mark

from api.host import find_existing_host
from app import db
from app.models import Host


ACCOUNT_NUMBER = "000102"


def create_host(canonical_facts):
    host = Host(canonical_facts, display_name=None, account=ACCOUNT_NUMBER)
    db.session.add(host)
    db.session.commit()
    return host


# FIXME: DRY
def generate_uuid():
    return str(uuid.uuid4())


def basic_host_dedup_test(initial_canonical_facts, search_canonical_facts):
    original_host = create_host(initial_canonical_facts)

    found_host = find_existing_host(ACCOUNT_NUMBER, search_canonical_facts)

    assert original_host.id == found_host.id


def test_find_host_using_subset_canonical_fact_match(flask_app_fixture):
    fqdn = "fred.flintstone.com"
    canonical_facts = {"fqdn": fqdn,
                       "bios_uuid": generate_uuid(),
                       "rhel_machine_id": generate_uuid(),
                       }

    # Create the subset of canonical facts to search by
    subset_canonical_facts = {"fqdn": fqdn}

    basic_host_dedup_test(canonical_facts, subset_canonical_facts)


def test_find_host_using_superset_canonical_fact_match(flask_app_fixture):
    canonical_facts = {"fqdn": "fred",
                       "bios_uuid": generate_uuid()}

    # Create the superset of canonical facts to search by
    superset_canonical_facts = canonical_facts.copy()
    superset_canonical_facts["rhel_machine_id"] = generate_uuid()
    superset_canonical_facts["satellite_id"] = generate_uuid()

    basic_host_dedup_test(canonical_facts, superset_canonical_facts)


def test_find_host_using_insights_id_match(flask_app_fixture):
    canonical_facts = {"fqdn": "fred",
                       "bios_uuid": generate_uuid(),
                       "insights_id": generate_uuid(),
                       }

    # Change the canonical facts except the insights_id...match on insights_id
    search_canonical_facts = {"fqdn": "barney",
                              "bios_uuid": generate_uuid(),
                              "insights_id": canonical_facts["insights_id"],
                              }

    basic_host_dedup_test(canonical_facts, search_canonical_facts)


def test_find_host_using_subscription_manager_id_match(flask_app_fixture):
    canonical_facts = {"fqdn": "fred",
                       "bios_uuid": generate_uuid(),
                       "subscription_manager_id": generate_uuid(),
                       }

    # Change the bios_uuid so that falling back to subset match will fail
    search_canonical_facts = {
        "bios_uuid": generate_uuid(),
        "subscription_manager_id": canonical_facts["subscription_manager_id"]
    }

    basic_host_dedup_test(canonical_facts, search_canonical_facts)


@mark.parametrize(("host_create_order", "expected_host"), (((0, 1), 1), ((1, 0), 0)))
def test_find_host_using_elevated_ids_match(
    flask_app_fixture, host_create_order, expected_host
):
    hosts_canonical_facts = (
        {"subscription_manager_id": generate_uuid()},
        {"insights_id": generate_uuid()},
    )

    created_hosts = []
    for host_canonical_facts in host_create_order:
        created_host = create_host(hosts_canonical_facts[host_canonical_facts])
        created_hosts.append(created_host)

    search_canonical_facts = {
        key: value
        for host_canonical_facts in hosts_canonical_facts
        for key, value in host_canonical_facts.items()
    }
    found_host = find_existing_host(ACCOUNT_NUMBER, search_canonical_facts)

    assert created_hosts[expected_host].id == found_host.id
