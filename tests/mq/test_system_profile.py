from __future__ import annotations

import json
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.exceptions import InventoryException
from app.models import db
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import SystemProfileMessageConsumer
from lib.host_repository import AddHostResult
from tests.helpers.db_utils import create_reference_host_in_db
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import OWNER_ID
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import valid_system_profile


@pytest.mark.parametrize("id_type", ("id", "insights_id"))
def test_update_system_profile(mq_create_or_update_host, db_get_host, id_type):
    expected_ids = {"insights_id": generate_uuid(), "fqdn": "foo.test.redhat.com"}
    input_host = base_host(
        **expected_ids,
        system_profile={
            "owner_id": OWNER_ID,
            "number_of_cpus": 1,
            "rhsm": {"version": "9.1", "environment_ids": ["01fd642e02de4e6da2da6172081a971e"]},
            "workloads": {"rhel_ai": {"variant": "RHEL AI"}, "crowdstrike": {"falcon_version": "7.0.1"}},
        },
    )
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)
    expected_ids["id"] = str(first_host_from_db.id)

    assert str(first_host_from_db.insights_id) == expected_ids["insights_id"]
    assert first_host_from_db.static_system_profile.number_of_cpus == 1

    input_host = base_host(
        **{id_type: expected_ids[id_type]},
        system_profile={
            "number_of_cpus": 4,
            "number_of_sockets": 8,
            "rhsm": {"version": "8.7"},
            "workloads": {"crowdstrike": {"falcon_version": "7.2.2"}},
        },
    )
    input_host.reporter = None
    second_host_from_event = mq_create_or_update_host(input_host, consumer_class=SystemProfileMessageConsumer)
    second_host_from_db = db_get_host(second_host_from_event.id)

    # The second host should have the same ID and insights ID,
    # and the system profile should have updated with the new values.
    assert str(second_host_from_db.id) == first_host_from_event.id
    assert str(second_host_from_db.insights_id) == expected_ids["insights_id"]

    # Verify core fields are updated correctly in normalized tables
    assert str(second_host_from_db.static_system_profile.owner_id) == OWNER_ID
    assert second_host_from_db.static_system_profile.number_of_cpus == 4
    assert second_host_from_db.static_system_profile.number_of_sockets == 8
    assert second_host_from_db.static_system_profile.rhsm == {
        "version": "8.7",
        "environment_ids": ["01fd642e02de4e6da2da6172081a971e"],
    }
    assert second_host_from_db.dynamic_system_profile.workloads == {
        "rhel_ai": {"variant": "RHEL AI"},
        "crowdstrike": {"falcon_version": "7.2.2"},
    }


@pytest.mark.usefixtures("db_get_host")
def test_update_system_profile_not_found(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    expected_insights_id = generate_uuid()
    input_host = base_host(
        insights_id=expected_insights_id, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1}
    )
    mq_create_or_update_host(input_host)

    input_host = base_host(insights_id=generate_uuid(), system_profile={"number_of_cpus": 4, "number_of_sockets": 8})

    # Should raise an exception due to missing host
    with pytest.raises(InventoryException):
        mq_create_or_update_host(
            input_host,
            notification_event_producer=mock_notification_event_producer,
            consumer_class=SystemProfileMessageConsumer,
        )
    mock_notification_event_producer.write_event.assert_called_once()


def test_update_system_profile_not_provided(mocker, mq_create_or_update_host, db_get_host):
    expected_ids = {"insights_id": generate_uuid(), "fqdn": "foo.test.redhat.com"}
    input_host = minimal_host(**expected_ids, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1})
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)
    mock_notification_event_producer = mocker.Mock()

    input_host = minimal_host(id=str(first_host_from_db.id), system_profile={})

    with pytest.raises(InventoryException):
        mq_create_or_update_host(
            input_host,
            notification_event_producer=mock_notification_event_producer,
            consumer_class=SystemProfileMessageConsumer,
        )
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.parametrize("platform_metadata", (None, {}, {"request_id": "12345"}))
def test_update_system_profile_no_identity(mocker, platform_metadata, db_create_host, system_profile_consumer_mock):
    message = wrap_message(
        minimal_host(account="foobar", system_profile={"number_of_cpus": 4}).data(), "add_host", platform_metadata
    )

    # We don't care about the values here
    mocker.patch(
        "lib.host_repository.update_system_profile",
        return_value=(
            db_create_host(),
            AddHostResult.updated,
        ),
    )

    # Just make sure it doesn't complain about missing Identity/metadata
    system_profile_consumer_mock.handle_message(json.dumps(message))


def test_update_system_profile_host_not_found(mocker, flask_app):
    message = json.dumps(
        wrap_message(
            minimal_host(org_id="nomatch", account="nomatch", system_profile={"number_of_cpus": 4}).data(),
            "add_host",
            get_platform_metadata(),
        )
    )

    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage(message=message)]

    consumer = SystemProfileMessageConsumer(fake_consumer, flask_app, mocker.Mock(), mocker.Mock())

    # Make sure the "not found" exception is properly handled
    consumer.event_loop(interrupt=mocker.Mock(side_effect=(False, True)))


@pytest.mark.parametrize("id_type", ("id", "insights_id"))
def test_log_update_system_profile(mq_create_or_update_host, db_get_host, id_type, caplog):
    caplog.at_level(logging.INFO)
    expected_ids = {"insights_id": generate_uuid(), "fqdn": "foo.test.redhat.com"}
    input_host = base_host(**expected_ids, system_profile={"owner_id": OWNER_ID, "number_of_cpus": 1})
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)
    expected_ids["id"] = str(first_host_from_db.id)

    assert str(first_host_from_db.insights_id) == expected_ids["insights_id"]
    assert first_host_from_db.static_system_profile.number_of_cpus == 1

    input_host = base_host(
        **{id_type: expected_ids[id_type]}, system_profile={"number_of_cpus": 4, "number_of_sockets": 8}
    )
    input_host.reporter = None
    second_host_from_event = mq_create_or_update_host(input_host, consumer_class=SystemProfileMessageConsumer)
    second_host_from_db = db_get_host(second_host_from_event.id)

    # The second host should have the same ID and insights ID,
    # and the system profile should have updated with the new values.
    assert str(second_host_from_db.id) == first_host_from_event.id
    assert str(second_host_from_db.insights_id) == expected_ids["insights_id"]
    # Verify normalized tables have updated values
    assert str(second_host_from_db.static_system_profile.owner_id) == OWNER_ID
    assert second_host_from_db.static_system_profile.number_of_cpus == 4
    assert second_host_from_db.static_system_profile.number_of_sockets == 8
    assert caplog.records[-1].message.startswith(f"System profile updated for host ID: {first_host_from_event.id}")
    assert caplog.records[-1].system_profile == "{}"


def test_update_system_profile_bios_fields(mq_create_or_update_host, db_get_host):
    # Create a host with bios_vendor set and no bios_version
    input_host = base_host(
        insights_id=generate_uuid(),
        fqdn="foo.test.redhat.com",
        system_profile={
            "owner_id": OWNER_ID,
            "bios_vendor": "old_vendor",
            "workloads": {
                "ansible": {
                    "catalog_worker_version": "1.2.3",
                    "controller_version": "1.2.3",
                    "hub_version": "1.2.3",
                    "sso_version": "1.2.3",
                },
                "crowdstrike": {
                    "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                    "falcon_backend": "auto",
                    "falcon_version": "7.14.16703.0",
                },
                "ibm_db2": {"is_running": True},
                "intersystems": {"is_intersystems": True, "running_instances": []},
                "mssql": {"version": "15.2.0"},
                "oracle_db": {"is_running": True},
                "rhel_ai": {
                    "variant": "RHEL AI",
                    "rhel_ai_version_id": "v1.1.3",
                    "gpu_models": [],
                    "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
                    "free_disk_storage": "3TB",
                },
                "sap": {
                    "sap_system": True,
                    "sids": ["ABC", "XYZ"],
                    "instance_number": "10",
                    "version": "1.00.122.04.1478575636",
                },
            },
        },
    )
    first_host_from_event = mq_create_or_update_host(input_host)
    first_host_from_db = db_get_host(first_host_from_event.id)

    assert first_host_from_db.static_system_profile.bios_vendor == "old_vendor"
    assert first_host_from_db.static_system_profile.bios_version is None

    # Update only system_profile with bios_vendor and bios_version
    input_host = base_host(
        id=str(first_host_from_db.id),
        system_profile={
            "bios_vendor": "new_vendor",
            "bios_version": "1.23",
        },
    )
    input_host.reporter = None
    second_host_from_event = mq_create_or_update_host(input_host, consumer_class=SystemProfileMessageConsumer)
    second_host_from_db = db_get_host(second_host_from_event.id)

    # Verify same host and merged/updated system profile
    assert str(second_host_from_db.id) == first_host_from_event.id
    assert str(second_host_from_db.static_system_profile.owner_id) == OWNER_ID
    assert second_host_from_db.static_system_profile.bios_vendor == "new_vendor"
    assert second_host_from_db.static_system_profile.bios_version == "1.23"


def test_batch_50_messages_no_system_profile_accumulation(mocker, event_producer, flask_app):
    """OOM regression test: host lookup queries must NOT eagerly load system profiles.

    The production OOM was caused by joinedload of HostStaticSystemProfile and
    HostDynamicSystemProfile during host lookup (multiple_canonical_facts_host_query).
    With 50 hosts per batch, each carrying large system profiles (installed_packages,
    network_interfaces, disk_devices, etc.), the session identity map grew to several GiB.

    This test detects the issue via SQL interception (not memory pressure), so
    any system profile payload is sufficient to trigger the same JOINs:
    1. Pre-create 50 hosts in the DB with system profiles.
    2. Send update messages for those same hosts through the consumer.
    3. Intercept every SQL statement and assert that NONE JOIN the
       system_profiles_static or system_profiles_dynamic tables.
    4. Also verify the identity map contains no system profile ORM objects.

    write_message_batch is mocked out so serialization (which legitimately
    lazy-loads system profiles) does not run — isolating the lookup phase.
    """
    from sqlalchemy import event as sqlevent

    from app.models.system_profile_dynamic import HostDynamicSystemProfile
    from app.models.system_profile_static import HostStaticSystemProfile

    batch_size = 50

    insights_ids = [generate_uuid() for _ in range(batch_size)]
    stale_ts = now() + timedelta(days=7)

    for iid in insights_ids:
        create_reference_host_in_db(iid, "puptoo", valid_system_profile(), stale_ts)

    db.session.expire_all()

    hosts = [
        minimal_host(
            insights_id=iid,
            system_profile={"number_of_cpus": 8},
        ).data()
        for iid in insights_ids
    ]
    msgs = [json.dumps(wrap_message(host, "add_host", get_platform_metadata())) for host in hosts]

    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=batch_size,
            mq_db_batch_max_seconds=5,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
        ),
    )
    mocker.patch("app.queue.host_mq.write_message_batch")

    captured_sql: list[str] = []

    def _capture_sql(conn, clauseelement, multiparams, params, execution_options):  # noqa: ARG001
        captured_sql.append(str(clauseelement))

    sqlevent.listen(db.engine, "before_execute", _capture_sql)
    try:
        fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage(message=msg) for msg in msgs], []]})

        consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, mocker.Mock())
        consumer.event_loop(mocker.Mock(side_effect=(False, True)))
    finally:
        sqlevent.remove(db.engine, "before_execute", _capture_sql)

    assert captured_sql, "No SQL was captured; host lookup/processing path may not have been executed"

    eager_load_queries = [
        sql
        for sql in captured_sql
        if ("system_profiles_static" in sql.lower() or "system_profiles_dynamic" in sql.lower())
        and "join" in sql.lower()
    ]
    assert not eager_load_queries, (
        f"Found {len(eager_load_queries)} SQL queries JOINing system profile tables during batch "
        f"processing. This means system profiles are being eagerly loaded (e.g. via joinedload), "
        f"which will cause OOM in production.\n\nOffending queries:\n" + "\n---\n".join(eager_load_queries[:3])
    )

    identity_map_types = {type(obj) for obj in db.session.identity_map.values()}
    assert HostStaticSystemProfile not in identity_map_types, (
        "HostStaticSystemProfile found in identity map — system profiles are being eagerly loaded."
    )
    assert HostDynamicSystemProfile not in identity_map_types, (
        "HostDynamicSystemProfile found in identity map — system profiles are being eagerly loaded."
    )
