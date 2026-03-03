from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pytest
from iqe.utils.blockers import iqe_blocker
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.base import NO_VALUE

from iqe_host_inventory.utils.datagen_utils import generate_canonical_facts
from iqe_host_inventory.utils.datagen_utils import generate_facts
from iqe_host_inventory.utils.datagen_utils import generate_per_reporter_staleness
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import rand_str
from iqe_host_inventory.utils.db_utils import Group
from iqe_host_inventory.utils.db_utils import Host
from iqe_host_inventory.utils.db_utils import HostGroupAssoc
from iqe_host_inventory.utils.db_utils import minimal_db_group
from iqe_host_inventory.utils.db_utils import minimal_db_host
from iqe_host_inventory.utils.db_utils import minimal_db_host_group_assoc
from iqe_host_inventory.utils.db_utils import query_associations_by_host_ids
from iqe_host_inventory.utils.db_utils import query_groups_by_ids
from iqe_host_inventory.utils.db_utils import query_hosts_by_ids
from iqe_host_inventory.utils.tag_utils import convert_tag_from_nested_to_structured

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_db_rhsm_schema_changes(inventory_db_session):
    """
    This test covers breaking schema changes that might lead to RHSM app become useless.

    The RHSM team has an app that is coupled to a read-only copy of the HBI DB.
    DB query: https://github.com/RedHatInsights/rhsm-subscriptions/blob/main/src/main/java/org/candlepin/subscriptions/inventory/db/model/InventoryHost.java#L90 # noqa: E501

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-3468

    1. Submit a specific query to the HBI database
    2. Make sure that no errors or exceptions occurs

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Inventory API: Ensure that the database schema changes
            will not broke external apps.
    """  # noqa: E501
    query = (
        "select h.id as inventory_id, h.org_id, h.modified_on, "
        "h.account, h.display_name, h.insights_id, h.subscription_manager_id, "
        "h.facts->'rhsm'->>'orgId' as org_id, "
        "h.facts->'rhsm'->>'IS_VIRTUAL' as is_virtual, "
        "h.facts->'rhsm'->>'VM_HOST_UUID' as hypervisor_uuid, "
        "h.facts->'satellite'->>'virtual_host_uuid' as satellite_hypervisor_uuid, "
        "h.facts->'satellite'->>'system_purpose_role' as satellite_role, "
        "h.facts->'satellite'->>'system_purpose_sla' as satellite_sla, "
        "h.facts->'satellite'->>'system_purpose_usage' as satellite_usage, "
        "h.facts->'rhsm'->>'GUEST_ID' as guest_id, "
        "h.facts->'rhsm'->>'SYNC_TIMESTAMP' as sync_timestamp, "
        "h.facts->'rhsm'->>'SYSPURPOSE_ROLE' as syspurpose_role, "
        "h.facts->'rhsm'->>'SYSPURPOSE_SLA' as syspurpose_sla, "
        "h.facts->'rhsm'->>'SYSPURPOSE_USAGE' as syspurpose_usage, "
        "h.facts->'rhsm'->>'SYSPURPOSE_UNITS' as syspurpose_units, "
        "h.facts->'rhsm'->>'BILLING_MODEL' as  billing_model, "
        "h.facts->'qpc'->>'IS_RHEL' as is_rhel, "
        "sps.infrastructure_type as system_profile_infrastructure_type, "
        "sps.cores_per_socket::text as system_profile_cores_per_socket, "
        "sps.number_of_sockets::text as system_profile_sockets, "
        "sps.cloud_provider as cloud_provider, "
        "sps.arch as system_profile_arch, "
        "sps.is_marketplace::text as is_marketplace, "
        "rhsm_products.products, "
        "qpc_prods.qpc_products, "
        "qpc_certs.qpc_product_ids, "
        "system_profile.system_profile_product_ids, "
        "h.stale_timestamp "
        "from hosts h "
        "left join system_profiles_static sps on h.org_id = sps.org_id and h.id = sps.host_id "
        "left join system_profiles_dynamic spd on h.org_id = spd.org_id and h.id = spd.host_id "
        "cross join lateral ( "
        "    select string_agg(items, ',') as products "
        "    from jsonb_array_elements_text(h.facts->'rhsm'->'RH_PROD') as items) rhsm_products "
        "cross join lateral ( "
        "    select string_agg(items, ',') as qpc_products "
        "    from jsonb_array_elements_text(h.facts->'qpc'->'rh_products_installed') as items) qpc_prods "  # noqa: E501
        "cross join lateral ( "
        "    select string_agg(items, ',') as qpc_product_ids "
        "    from jsonb_array_elements_text(h.facts->'qpc'->'rh_product_certs') as items) qpc_certs "  # noqa: E501
        "cross join lateral ( "
        "    select string_agg(items->>'id', ',') as system_profile_product_ids "
        "    from jsonb_array_elements(spd.installed_products) as items) system_profile "
        "where h.org_id IN ('00000000')"
        "   and (h.facts->'rhsm'->>'BILLING_MODEL' IS NULL OR h.facts->'rhsm'->>'BILLING_MODEL' <> 'marketplace')"  # noqa: E501
        "   and (h.host_type IS NULL OR h.host_type <> 'edge')"
        "   and (stale_timestamp is null "
        "   or  (NOW() < stale_timestamp + make_interval(days => 30)))"
    )

    inventory_db_session.execute(query)


def get_db_object_attrs(obj: Host | Group | HostGroupAssoc) -> dict[str, Any]:
    ob_inspect = inspect(obj)
    return {
        attr.key: attr.loaded_value
        for attr in ob_inspect.attrs
        if attr.loaded_value is not NO_VALUE
    }


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_db_schema_hosts_minimal(inventory_db_session):
    """
    Check DB Hosts table schema with nullable fields

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Check DB Hosts table schema with nullable fields
    """
    host = minimal_db_host(empty_strings=True)
    host_attrs = get_db_object_attrs(host)

    inventory_db_session.add(host)
    inventory_db_session.commit()

    created_host = query_hosts_by_ids(inventory_db_session, [host.id])[0]
    created_attrs = get_db_object_attrs(created_host)

    assert all(key in created_attrs for key in host_attrs.keys())
    for key, value in created_attrs.items():
        if key in host_attrs:
            if isinstance(value, UUID):
                assert host_attrs[key] == str(value)
            else:
                assert host_attrs[key] == value
        elif key == "per_reporter_staleness":
            assert value == {}
        else:
            assert value is None


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_db_schema_hosts_max_len(inventory_db_session):
    """
    Check DB Hosts table schema maximum string length

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Check DB Hosts table schema maximum string length
    """
    reporter = generate_string_of_length(255)
    groups = [minimal_db_group(as_dict=True) for _ in range(5)]
    for group in groups:
        group["created_on"] = group["created_on"].isoformat()
        group["modified_on"] = group["modified_on"].isoformat()
    tags = {
        rand_str(): {
            rand_str(): [rand_str(), rand_str()],
            rand_str(): [rand_str()],
            rand_str(): [],
        }
    }
    canonical_facts = generate_canonical_facts()
    host = minimal_db_host(
        account=generate_string_of_length(10),
        org_id=generate_string_of_length(36),
        display_name=generate_string_of_length(200),
        ansible_host=generate_string_of_length(255),
        facts=generate_facts(),
        tags=tags,
        tags_alt=convert_tag_from_nested_to_structured(tags),
        **canonical_facts,
        groups=groups,
        reporter=reporter,
        per_reporter_staleness=generate_per_reporter_staleness(reporter),
    )
    host_attrs = get_db_object_attrs(host)

    inventory_db_session.add(host)
    inventory_db_session.commit()

    created_host = query_hosts_by_ids(inventory_db_session, [host.id])[0]
    created_attrs = get_db_object_attrs(created_host)

    assert set(created_attrs.keys()) == set(host_attrs.keys())
    for key, value in created_attrs.items():
        if isinstance(value, UUID):
            assert host_attrs[key] == str(value)
        else:
            assert host_attrs[key] == value


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_db_schema_groups_minimal(inventory_db_session):
    """
    Check DB Groups table schema with nullable fields

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Check DB Groups table schema with nullable fields
    """
    group = minimal_db_group(empty_strings=True)
    group_attrs = get_db_object_attrs(group)

    inventory_db_session.add(group)
    inventory_db_session.commit()

    created_group = query_groups_by_ids(inventory_db_session, [group.id])[0]
    created_attrs = get_db_object_attrs(created_group)

    assert all(key in created_attrs for key in group_attrs.keys())
    for key, value in created_attrs.items():
        if key in group_attrs:
            if key == "id":
                assert group_attrs[key] == str(value)
            else:
                assert group_attrs[key] == value
        else:
            assert value is None


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_db_schema_groups_max_len(inventory_db_session):
    """
    Check DB Groups table schema maximum string length

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Check DB Groups table schema maximum string length
    """
    group = minimal_db_group(
        account=generate_string_of_length(10),
        org_id=generate_string_of_length(36),
        name=generate_string_of_length(255),
    )
    group_attrs = get_db_object_attrs(group)

    inventory_db_session.add(group)
    inventory_db_session.commit()

    created_group = query_groups_by_ids(inventory_db_session, [group.id])[0]
    created_attrs = get_db_object_attrs(created_group)

    assert set(created_attrs.keys()) == set(group_attrs.keys())
    for key, value in created_attrs.items():
        if key == "id":
            assert group_attrs[key] == str(value)
        else:
            assert group_attrs[key] == value


@iqe_blocker(iqe_blocker.jira("RHINENG-18981", category=iqe_blocker.PRODUCT_RFE))
@pytest.mark.smoke
@pytest.mark.ephemeral
def test_db_schema_hosts_groups_correct(inventory_db_session):
    """
    Check DB Hosts_Groups partitioned table schema - correct values

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Check DB Hosts_Groups table schema - correct values
    """
    host = minimal_db_host()
    group = minimal_db_group()
    inventory_db_session.add_all([host, group])
    inventory_db_session.commit()

    association = minimal_db_host_group_assoc(str(host.org_id), str(host.id), str(group.id))
    association_attrs = get_db_object_attrs(association)

    inventory_db_session.add(association)
    inventory_db_session.commit()

    created_assoc = query_associations_by_host_ids(inventory_db_session, [association.host_id])[0]
    created_attrs = get_db_object_attrs(created_assoc)

    assert set(created_attrs.keys()) == set(association_attrs.keys())
    for key, value in created_attrs.items():
        assert association_attrs[key] == str(value)


@iqe_blocker(iqe_blocker.jira("RHINENG-18981", category=iqe_blocker.PRODUCT_RFE))
@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("id_key", ["org_id, host_id", "group_id"])
def test_db_schema_hosts_groups_foreign_keys(inventory_db_session, id_key):
    """
    Check that IDs in DB Hosts_Groups partitioned table schema are foreign keys

    JIRA: https://issues.redhat.com/browse/ESSNTL-3824

    metadata:
        requirements: inv-db-schema
        assignee: fstavela
        importance: high
        title: Check DB Hosts_Groups table schema - foreign keys
    """
    host = minimal_db_host()
    group = minimal_db_group()
    inventory_db_session.add_all([host, group])
    inventory_db_session.commit()

    association = minimal_db_host_group_assoc(
        str(host.org_id) if id_key != "org_id, host_id" else generate_string_of_length(36),
        str(host.id) if id_key != "org_id, host_id" else generate_uuid(),
        str(group.id) if id_key != "group_id" else generate_uuid(),
    )
    org_id = association.org_id
    host_id = association.host_id
    group_id = association.group_id

    with pytest.raises(IntegrityError) as exc:
        inventory_db_session.add(association)
        inventory_db_session.commit()

    key_value = f"{org_id}, {host_id}" if id_key == "org_id, host_id" else group_id
    fk = "fk_hosts_groups_on_hosts" if id_key == "org_id, host_id" else "fk_hosts_groups_on_groups"
    table = "hosts" if id_key == "org_id, host_id" else "groups"

    error_message = str(exc.value.orig)
    assert 'insert or update on table "hosts_groups_p' in error_message
    assert (
        f'"{fk}"\nDETAIL:  Key ({id_key})=({key_value}) is not present in table "{table}".\n'
    ) in error_message
