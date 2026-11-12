"""Raw PostgreSQL contracts, independent of application constructor defaults.

Each contract runs against both the db.create_all() schema the test suite uses and a
database built by the Alembic migrations, which is what deployments actually run.
"""

from datetime import UTC
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import db
from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import include_object

HOST_COLUMNS = [
    "id",
    "account",
    "org_id",
    "display_name",
    "ansible_host",
    "insights_id",
    "subscription_manager_id",
    "satellite_id",
    "fqdn",
    "bios_uuid",
    "ip_addresses",
    "mac_addresses",
    "provider_id",
    "provider_type",
    "created_on",
    "modified_on",
    "facts",
    "tags",
    "tags_alt",
    "groups",
    "last_check_in",
    "reporter",
    "per_reporter_staleness",
]
GROUP_COLUMNS = ["id", "account", "org_id", "name", "created_on", "modified_on"]
TIMESTAMP = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture(params=["models", "migrations"])
def raw_db(request, flask_app):  # noqa: ARG001
    engine = db.engine if request.param == "models" else request.getfixturevalue("migrated_database")
    with engine.connect() as conn:
        # Reflection avoids Python-side defaults, validators and JSON normalization.
        metadata = MetaData(schema=INVENTORY_SCHEMA)
        tables = {
            name: Table(name, metadata, autoload_with=conn, resolve_fks=False)
            for name in ("hosts", "groups", "hosts_groups")
        }
        # Nothing is committed, so neither database needs cleanup.
        yield SimpleNamespace(conn=conn, tables=tables, migrated=request.param == "migrations")
        conn.rollback()


def test_models_match_migrations(migrated_database):
    # The same comparison `flask db migrate` autogenerates from; server defaults are not compared.
    with migrated_database.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"include_schemas": True, "include_object": include_object, "compare_type": True}
        )
        assert compare_metadata(context, db.metadata) == []


def _host_values(**values):
    return {
        "id": uuid4(),
        "org_id": "schema-host",
        "reporter": "schema-test",
        "insights_id": UUID(int=0),
        "created_on": TIMESTAMP,
        "modified_on": TIMESTAMP,
        "last_check_in": TIMESTAMP,
        "groups": [],
        **values,
    }


def _group_values(**values):
    return {
        "id": uuid4(),
        "org_id": "schema-group",
        "name": "schema-test",
        "created_on": TIMESTAMP,
        "modified_on": TIMESTAMP,
        # Not part of IQE's independent mapping. The model lacks the migration's
        # server default for this newer required column, so supply test scaffolding.
        "ungrouped": False,
        **values,
    }


def test_raw_host_minimal_defaults(raw_db):
    hosts = raw_db.tables["hosts"]
    values = _host_values(org_id="", reporter="")
    raw_db.conn.execute(hosts.insert().values(**values))
    row = (
        raw_db.conn.execute(select(*(hosts.c[key] for key in HOST_COLUMNS)).where(hosts.c.id == values["id"]))
        .mappings()
        .one()
    )
    expected = {key: None for key in HOST_COLUMNS}
    expected.update(values, per_reporter_staleness={})
    assert dict(row) == expected


def test_raw_host_maximum_lengths_round_trip(raw_db):
    hosts = raw_db.tables["hosts"]
    reporter = "r" * 255
    tags = {"schema": {"role": ["web", "db"], "empty": []}}
    groups = [
        {
            "id": str(uuid4()),
            "org_id": "schema-host",
            "account": None,
            "name": f"group-{i}",
            "created_on": TIMESTAMP.isoformat(),
            "modified_on": TIMESTAMP.isoformat(),
        }
        for i in range(5)
    ]
    values = _host_values(
        account="a" * 10,
        org_id="o" * 36,
        display_name="d" * 200,
        ansible_host="h" * 255,
        reporter=reporter,
        insights_id=uuid4(),
        subscription_manager_id=str(uuid4()),
        satellite_id=str(uuid4()),
        bios_uuid=str(uuid4()),
        fqdn="schema.example.com",
        ip_addresses=["192.0.2.1"],
        mac_addresses=["aa:bb:cc:dd:ee:ff"],
        provider_id="instance-123",
        provider_type="aws",
        facts={"schema": {"nested": {"key": "value"}}},
        tags=tags,
        tags_alt=[
            {"namespace": "schema", "key": "role", "value": "web"},
            {"namespace": "schema", "key": "role", "value": "db"},
            {"namespace": "schema", "key": "empty", "value": None},
        ],
        groups=groups,
        per_reporter_staleness={reporter: TIMESTAMP.isoformat()},
    )
    raw_db.conn.execute(hosts.insert().values(**values))
    row = (
        raw_db.conn.execute(select(*(hosts.c[key] for key in HOST_COLUMNS)).where(hosts.c.id == values["id"]))
        .mappings()
        .one()
    )
    assert dict(row) == values


@pytest.mark.parametrize("maximum_lengths", [False, True], ids=["minimal", "maximum-lengths"])
def test_raw_group_round_trip(raw_db, maximum_lengths):
    groups = raw_db.tables["groups"]
    values = _group_values(name="")
    if maximum_lengths:
        values.update(account="a" * 10, org_id="o" * 36, name="g" * 255)
    raw_db.conn.execute(groups.insert().values(**values))
    row = (
        raw_db.conn.execute(select(*(groups.c[key] for key in GROUP_COLUMNS)).where(groups.c.id == values["id"]))
        .mappings()
        .one()
    )
    assert dict(row) == {key: values.get(key) for key in GROUP_COLUMNS}


def test_raw_association_accepts_independent_group_org(raw_db):
    host = _host_values(per_reporter_staleness={})
    group = _group_values()
    raw_db.conn.execute(raw_db.tables["hosts"].insert().values(**host))
    raw_db.conn.execute(raw_db.tables["groups"].insert().values(**group))
    association = {"org_id": host["org_id"], "host_id": host["id"], "group_id": group["id"]}
    raw_db.conn.execute(raw_db.tables["hosts_groups"].insert().values(**association))
    # Physical FK is group_id-only; this is not an application authorization assertion.
    assert host["org_id"] != group["org_id"]
    row = raw_db.conn.execute(select(raw_db.tables["hosts_groups"])).mappings().one()
    assert dict(row) == association


def test_raw_association_foreign_keys(raw_db, subtests):
    host = _host_values(per_reporter_staleness={})
    group = _group_values()
    raw_db.conn.execute(raw_db.tables["hosts"].insert().values(**host))
    raw_db.conn.execute(raw_db.tables["groups"].insert().values(**group))
    # Migrations partition hosts_groups, so the violation is reported by a partition.
    association_table = "hosts_groups_p" if raw_db.migrated else "hosts_groups"
    for invalid_key, table, constraint in [
        ("host", "hosts", "fk_hosts_groups_on_hosts"),
        ("group", "groups", "fk_hosts_groups_on_groups"),
    ]:
        association = {"org_id": host["org_id"], "host_id": host["id"], "group_id": group["id"]}
        if invalid_key == "host":
            association.update(org_id="missing-org", host_id=uuid4())
        else:
            association["group_id"] = uuid4()
        with subtests.test(invalid_key=invalid_key):
            with pytest.raises(IntegrityError) as exc, raw_db.conn.begin_nested():
                raw_db.conn.execute(raw_db.tables["hosts_groups"].insert().values(**association))
            diagnostic = exc.value.orig.diag
            assert diagnostic.constraint_name == constraint
            assert diagnostic.table_name.startswith(association_table)
            assert exc.value.orig.pgcode == "23503"
            detail = diagnostic.message_detail
            assert f'table "{table}"' in detail
            keys = ["org_id", "host_id"] if invalid_key == "host" else ["group_id"]
            assert f"({', '.join(keys)})" in detail
            for key in keys:
                assert str(association[key]) in detail


def test_rhsm_consumer_query_schema_compatibility(raw_db):
    # Same consumer query as IQE, including unqualified relation names and all lateral joins.
    raw_db.conn.execute(text(f'SET LOCAL search_path TO "{INVENTORY_SCHEMA}", public'))
    query = """
        select h.id as inventory_id, h.org_id, h.modified_on,
        h.account, h.display_name, h.insights_id, h.subscription_manager_id,
        h.facts->'rhsm'->>'orgId' as org_id,
        h.facts->'rhsm'->>'IS_VIRTUAL' as is_virtual,
        h.facts->'rhsm'->>'VM_HOST_UUID' as hypervisor_uuid,
        h.facts->'satellite'->>'virtual_host_uuid' as satellite_hypervisor_uuid,
        h.facts->'satellite'->>'system_purpose_role' as satellite_role,
        h.facts->'satellite'->>'system_purpose_sla' as satellite_sla,
        h.facts->'satellite'->>'system_purpose_usage' as satellite_usage,
        h.facts->'rhsm'->>'GUEST_ID' as guest_id,
        h.facts->'rhsm'->>'SYNC_TIMESTAMP' as sync_timestamp,
        h.facts->'rhsm'->>'SYSPURPOSE_ROLE' as syspurpose_role,
        h.facts->'rhsm'->>'SYSPURPOSE_SLA' as syspurpose_sla,
        h.facts->'rhsm'->>'SYSPURPOSE_USAGE' as syspurpose_usage,
        h.facts->'rhsm'->>'SYSPURPOSE_UNITS' as syspurpose_units,
        h.facts->'rhsm'->>'BILLING_MODEL' as billing_model,
        h.facts->'qpc'->>'IS_RHEL' as is_rhel,
        sps.infrastructure_type as system_profile_infrastructure_type,
        sps.cores_per_socket::text as system_profile_cores_per_socket,
        sps.number_of_sockets::text as system_profile_sockets,
        sps.cloud_provider as cloud_provider,
        sps.arch as system_profile_arch,
        sps.is_marketplace::text as is_marketplace,
        rhsm_products.products, qpc_prods.qpc_products, qpc_certs.qpc_product_ids,
        system_profile.system_profile_product_ids
        from hosts h
        left join system_profiles_static sps on h.org_id = sps.org_id and h.id = sps.host_id
        left join system_profiles_dynamic spd on h.org_id = spd.org_id and h.id = spd.host_id
        left join staleness s on h.org_id = s.org_id
        cross join lateral (
            select string_agg(items, ',') as products
            from jsonb_array_elements_text(h.facts->'rhsm'->'RH_PROD') as items) rhsm_products
        cross join lateral (
            select string_agg(items, ',') as qpc_products
            from jsonb_array_elements_text(h.facts->'qpc'->'rh_products_installed') as items) qpc_prods
        cross join lateral (
            select string_agg(items, ',') as qpc_product_ids
            from jsonb_array_elements_text(h.facts->'qpc'->'rh_product_certs') as items) qpc_certs
        cross join lateral (
            select string_agg(items->>'id', ',') as system_profile_product_ids
            from jsonb_array_elements(spd.installed_products) as items) system_profile
        where h.org_id IN ('00000000')
        and (h.facts->'rhsm'->>'BILLING_MODEL' IS NULL OR h.facts->'rhsm'->>'BILLING_MODEL' <> 'marketplace')
        and (h.host_type IS NULL OR h.host_type <> 'edge')
        and h.last_check_in + make_interval(secs => coalesce(s.conventional_time_to_stale,
            104400)) > NOW() - make_interval(secs => coalesce(s.conventional_time_to_delete, 2592000))
    """
    assert raw_db.conn.execute(text(query)).all() == []
