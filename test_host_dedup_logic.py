import uuid

from api.host import find_existing_host
from app import db
from app.models import Host
from test_utils import flask_app_fixture

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
    search_canonical_facts = {"bios_uuid": generate_uuid(), }
    search_canonical_facts["subscription_manager_id"] = canonical_facts["subscription_manager_id"]

    basic_host_dedup_test(canonical_facts, search_canonical_facts)


def test_find_host_using_elevated_ids_match(flask_app_fixture):
    first_canonical_facts = {"subscription_manager_id": generate_uuid()}
    create_host(first_canonical_facts)

    second_canonical_facts = {"insights_id": generate_uuid()}
    expected_host = create_host(second_canonical_facts)

    search_canonical_facts = {**first_canonical_facts, **second_canonical_facts}
    found_host = find_existing_host(ACCOUNT_NUMBER, search_canonical_facts)

    assert expected_host.id == found_host.id
