from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.queue.events import EventType
from app.queue.host_mq import IngressMessageConsumer
from tests.helpers.db_utils import create_reference_host_in_db
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.mq_utils import assert_mq_host_data
from tests.helpers.mq_utils import wrap_message
from tests.helpers.system_profile_utils import mock_system_profile_specification
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import OWNER_ID
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import YUM_REPO2
from tests.helpers.test_utils import generate_random_string
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import valid_system_profile


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_simple(mq_create_or_update_host):
    """
    Tests adding a host with some simple data
    """
    expected_insights_id = generate_uuid()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        display_name=generate_random_string(),
        system_profile={"owner_id": OWNER_ID},
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, _ = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_system_profile(mq_create_or_update_host):
    """
    Tests adding a host with message containing system profile
    """
    expected_insights_id = generate_uuid()
    expected_system_profile = valid_system_profile()
    expected_system_profile["owner_id"] = OWNER_ID

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        display_name=generate_random_string(),
        system_profile=expected_system_profile,
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_without_defer_to(models_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host without "defer_to" option - system profile should be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "puptoo", original_system_profile, puptoo_stale_timestamp
    )
    existing_host_id = existing_host.id
    returned_host = existing_host

    # Verify original profile was stored (check a key field in normalized tables)
    assert returned_host.static_system_profile is not None
    assert returned_host.static_system_profile.arch == original_system_profile.get("arch")

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    updated_host = mq_create_or_update_host(host)
    assert str(updated_host.id) == str(existing_host_id)

    returned_host = db_get_host(existing_host_id)
    # Verify updated profile in normalized tables
    # Check that key fields match the updated system profile
    assert returned_host.static_system_profile.arch == updated_system_profile.get("arch")
    # yum_repos should have the additional repo from updated_system_profile
    assert len(returned_host.static_system_profile.yum_repos) == len(updated_system_profile.get("yum_repos", []))


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_defer_to(models_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host with "defer_to" option - system profile should not be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "puptoo", original_system_profile, puptoo_stale_timestamp
    )
    existing_host_id = existing_host.id
    returned_host = db_get_host(existing_host_id)

    # Check that the original profile was stored in normalized tables
    assert returned_host.static_system_profile is not None

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    updated_host = mq_create_or_update_host(host, operation_args={"defer_to_reporter": "puptoo"})
    assert str(updated_host.id) == str(existing_host_id)

    returned_host = db_get_host(existing_host_id)
    # Verify profile was NOT updated (defer_to_reporter preserved original values)
    # Check a key field that would have changed if the update had been applied
    assert returned_host.static_system_profile.yum_repos != updated_system_profile.get("yum_repos")


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_defer_to_wrong_reporter(models_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host with "defer_to" option,
    but base host not reported by specified reporter - system profile should be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    stale_timestamp = models_datetime_mock + timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "yupana", original_system_profile, stale_timestamp
    )
    existing_host_id = existing_host.id
    returned_host = db_get_host(existing_host_id)

    # Verify original profile was stored in normalized tables
    assert returned_host.static_system_profile is not None

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    updated_host = mq_create_or_update_host(host, operation_args={"defer_to_reporter": "puptoo"})
    assert str(updated_host.id) == str(existing_host_id)

    returned_host = db_get_host(existing_host_id)
    # Verify profile WAS updated (defer_to didn't match, so update was applied)
    # The updated profile should have more yum_repos
    assert len(returned_host.static_system_profile.yum_repos or []) == len(updated_system_profile.get("yum_repos", []))


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_defer_to_stale(mq_create_or_update_host, db_get_host):
    """
    Tests adding (updating) a host with "defer_to" option, but reporter stale - system profile should be updated.
    """
    expected_insights_id = generate_uuid()
    original_system_profile = valid_system_profile(owner_id=OWNER_ID)
    updated_system_profile = valid_system_profile(owner_id=OWNER_ID, additional_yum_repo=YUM_REPO2)
    puptoo_stale_timestamp = now() - timedelta(days=1)

    existing_host = create_reference_host_in_db(
        expected_insights_id, "puptoo", original_system_profile, puptoo_stale_timestamp
    )
    existing_host_id = existing_host.id

    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=updated_system_profile,
    )

    # Make host stale here
    with patch("app.models.utils.datetime") as models_datetime:
        models_datetime.now.return_value = now() + timedelta(days=2)
        updated_host = mq_create_or_update_host(host, operation_args={"defer_to_reporter": "puptoo"})
        assert str(updated_host.id) == str(existing_host_id)
        returned_host = db_get_host(existing_host_id)
        # Verify profile WAS updated (stale reporter, so update was applied)
        # Check yum_repos count matches updated profile
        assert len(returned_host.static_system_profile.yum_repos or []) == len(
            updated_system_profile.get("yum_repos", [])
        )


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_tags(mq_create_or_update_host):
    """
    Tests adding a host with message containing tags
    """
    expected_insights_id = generate_uuid()
    expected_tags = [
        {"namespace": "NS1", "key": "key3", "value": "val3"},
        {"namespace": "NS3", "key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "Sat", "key": "dev", "value": ""},
        {"namespace": "Sat", "key": "test"},
        {"namespace": None, "key": "key", "value": "val1"},
        {"namespace": "", "key": "key", "value": "val4"},
        {"namespace": "null", "key": "key", "value": "val5"},
        {"namespace": None, "key": "only_key", "value": None},
        {"key": "just_key"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        display_name=generate_random_string(),
        tags=expected_tags,
    )

    expected_results = {"host": {**host.data()}}
    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)

    assert len(event["host"]["tags"]) == len(expected_tags)


@pytest.mark.parametrize(
    "tag",
    [
        {"namespace": "NS", "key": "", "value": "val"},
        {"namespace": "a" * 256, "key": "key", "value": "val"},
        {"namespace": "NS", "key": "a" * 256, "value": "val"},
        {"namespace": "NS", "key": "key", "value": "a" * 256},
        {"namespace": "NS", "key": None, "value": "a" * 256},
        {"namespace": "NS", "value": "a" * 256},
    ],
)
def test_add_host_with_invalid_tags(tag, mocker, mq_create_or_update_host):
    """
    Tests adding a host with message containing invalid tags
    """
    mock_notification_event_producer = mocker.Mock()
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=[tag])

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
def test_add_host_empty_keys_system_profile(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    system_profile = {"owner_id": OWNER_ID, "disk_devices": [{"options": {"": "invalid"}}]}
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
def test_add_host_with_invalid_system_update_method(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    system_profile = {"owner_id": OWNER_ID, "system_update_method": "Whooping-cranes"}
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.system_profile
@pytest.mark.parametrize(("baseurl",), (("http://www.example.com",), ("x" * 2049,)))
def test_add_host_yum_repos_baseurl_system_profile(mq_create_or_update_host, db_get_host, baseurl):
    yum_repo = {"name": "repo1", "gpgcheck": True, "enabled": True}
    host_to_create = minimal_host(
        account=SYSTEM_IDENTITY["account_number"], system_profile={"yum_repos": [{**yum_repo, "baseurl": baseurl}]}
    )
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.static_system_profile.yum_repos == [yum_repo]


@pytest.mark.system_profile
def test_add_host_type_coercion_system_profile(mq_create_or_update_host, db_get_host):
    host_to_create = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"number_of_cpus": "1"})
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)

    # Verify type coercion in normalized tables
    assert created_host_from_db.static_system_profile.number_of_cpus == 1
    assert str(created_host_from_db.static_system_profile.owner_id) == OWNER_ID


@pytest.mark.system_profile
def test_add_host_key_filtering_system_profile(mq_create_or_update_host, db_get_host):
    host_to_create = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        system_profile={
            "owner_id": OWNER_ID,
            "number_of_cpus": 1,
            "number_of_gpus": 2,
            "disk_devices": [{"options": {"uid": "0"}, "mount_options": {"ro": True}}],
        },
    )
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)
    # Check that system profile data is stored in normalized tables
    assert created_host_from_db.static_system_profile.number_of_cpus == 1
    assert str(created_host_from_db.static_system_profile.owner_id) == OWNER_ID
    assert created_host_from_db.static_system_profile.disk_devices == [{"options": {"uid": "0"}}]


def test_add_host_externalized_system_profile(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    orig_spec = system_profile_specification()
    mock_spec = deepcopy(orig_spec)
    mock_spec["$defs"]["SystemProfile"]["properties"]["number_of_cpus"]["minimum"] = 2

    with mock_system_profile_specification(mock_spec):
        host_to_create = minimal_host(account=SYSTEM_IDENTITY["account_number"], system_profile={"number_of_cpus": 1})
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host_to_create, notification_event_producer=mock_notification_event_producer)
        mock_notification_event_producer.write_event.assert_called_once()


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_operating_system(mq_create_or_update_host, db_get_host):
    """
    Tests that operating_system in the system profile is ingested properly
    """
    operating_system = {"major": 5, "minor": 1, "name": "RHEL"}
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        system_profile={"operating_system": operating_system, "owner_id": OWNER_ID},
    )
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.static_system_profile.operating_system == operating_system


@pytest.mark.usefixtures("event_datetime_mock", "db_get_host")
def test_add_host_with_operating_system_incorrect_format(mocker, mq_create_or_update_host):
    """
    Tests that operating_system in the system profile is rejected if it's in the wrong format
    """
    mock_notification_event_producer = mocker.Mock()
    operating_system_list = [
        {"major": "bananas", "minor": 1, "name": "RHEL"},
        {"major": 1, "minor": "oranges", "name": "RHEL"},
        {"major": 1, "minor": 1, "name": "UBUNTU"},
    ]
    for operating_system in operating_system_list:
        host = minimal_host(
            account=SYSTEM_IDENTITY["account_number"],
            system_profile={"operating_system": operating_system, "owner_id": OWNER_ID},
        )
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
        mock_notification_event_producer.write_event.assert_called()


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_sap_system(mq_create_or_update_host):
    expected_insights_id = generate_uuid()

    system_profile = valid_system_profile()
    # Update to use workloads structure for SAP data (stored in system_profiles_dynamic)
    system_profile["workloads"] = {"sap": {"sap_system": True}}
    system_profile["owner_id"] = OWNER_ID

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        display_name=generate_random_string(),
        insights_id=expected_insights_id,
        system_profile=system_profile,
    )

    expected_results = {"host": {**host.data()}}

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, _ = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_kafka_event_has_only_workloads_fields(mq_create_or_update_host):
    """Kafka events include only the workloads.* structure without legacy workload fields."""
    expected_insights_id = generate_uuid()
    system_profile = {
        "owner_id": OWNER_ID,
        "workloads": {
            "sap": {"sap_system": True, "sids": ["ABC", "XYZ"]},
            "mssql": {"version": "15.2.0"},
            "crowdstrike": {
                "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
                "falcon_backend": "kernel",
                "falcon_version": "7.14.16703.0",
            },
            "intersystems": {
                "is_intersystems": True,
                "running_instances": [
                    {"name": "HEALTH_PROD", "version": "2023.1", "path": "/opt/intersystems/iris/bin"}
                ],
            },
            "ansible": {
                "controller_version": "1.2.3",
                "hub_version": "1.2.3",
                "catalog_worker_version": "1.2.3",
                "sso_version": "1.2.3",
            },
        },
    }

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        system_profile=system_profile,
    )

    _, event, _ = mq_create_or_update_host(host, return_all_data=True)

    sp = event["host"]["system_profile"]
    assert sp["workloads"]["sap"]["sap_system"] is True
    assert sp["workloads"]["ansible"]["controller_version"] == "1.2.3"
    assert "sap" not in sp
    assert "sap_system" not in sp
    assert "sap_sids" not in sp
    assert "ansible" not in sp


@pytest.mark.parametrize("tags", ({}, {"tags": []}, {"tags": {}}))
def test_add_host_with_no_tags(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, **tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {}


def test_add_host_with_null_tags(mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(tags=None)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_add_host_with_tag_list(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = [
        {"namespace": "namespace 1", "key": "key 1", "value": "value 1"},
        {"namespace": "namespace 1", "key": "key 2", "value": None},
        {"namespace": "namespace 2", "key": "key 1", "value": None},
        {"namespace": "namespace 2", "key": "key 1", "value": ""},
        {"namespace": "namespace 2", "key": "key 1", "value": "value 2"},
        {"namespace": "", "key": "key 3", "value": "value 3"},
        {"namespace": None, "key": "key 3", "value": "value 4"},
        {"namespace": "null", "key": "key 3", "value": "value 5"},
    ]

    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {
        "namespace 1": {"key 1": ["value 1"], "key 2": []},
        "namespace 2": {"key 1": ["value 2"]},
        "null": {"key 3": ["value 3", "value 4", "value 5"]},
    }


def test_add_host_with_tag_dict(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = {
        "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": None},
        "namespace 2": {"key 1": ["value 2", "", None]},
        "namespace 3": None,
        "namespace 4": {},
        "null": {"key 4": ["value 3"]},
        "": {"key 4": ["value 4"]},
    }
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {
        "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": []},
        "namespace 2": {"key 1": ["value 2"]},
        "null": {"key 4": ["value 3", "value 4"]},
    }


@pytest.mark.parametrize(
    "tags",
    (
        "string",
        123,
        123.4,
        [["namespace", "key", "value"]],
        [{"namespace": {"key": ["value"]}}],
        {"namespace": ["key", ["value"]]},
        {"namespace": [["key", "value"]]},
        {"namespace": ["key", "value"]},
        {"namespace": "key"},
        {"namespace": {"key": "value"}},
        {"namespace": {"key": {"value": "eulav"}}},
        {"namespace": {"key": [["value"]]}},
        {"namespace": {"key": [{"value": "eulav"}]}},
        {"namespace": {"key": [123]}},
        {"namespace": {"key": [123.4]}},
        {"namespace": {"": ["value"]}},
    ),
)
def test_add_host_with_invalid_tags_2(tags, mocker, mq_create_or_update_host):
    mock_notification_event_producer = mocker.Mock()
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=tags)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_add_tags_to_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        ([{"namespace": "namespace 1", "key": "key 1", "value": "value 1"}], {"namespace 1": {"key 1": ["value 1"]}}),
        (
            [{"namespace": "namespace 2", "key": "key 1", "value": "value 2"}],
            {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_add_tags_to_host_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        ({"namespace 1": {"key 1": ["value 1"]}}, {"namespace 1": {"key 1": ["value 1"]}}),
        (
            {"namespace 2": {"key 1": ["value 2"]}},
            {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@pytest.mark.parametrize("tags", ({}, {"tags": []}, {"tags": {}}))
def test_add_host_default_empty_dict(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, **tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {}
    assert record.tags_alt == []


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_without_stale_timestamp(mq_create_or_update_host):
    """
    Tests to see if the host is successfully created without stale_timestamp.
    """
    expected_insights_id = generate_uuid()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
    )

    host_keys_to_check = ["reporter", "stale_timestamp", "culled_timestamp"]

    key, event, _ = mq_create_or_update_host(host, return_all_data=True)
    updated_timestamp = datetime.fromisoformat(event["host"]["last_check_in"])

    expected_results = {
        "host": {
            **host.data(),
            "stale_timestamp": (updated_timestamp + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)).isoformat(),
            "stale_warning_timestamp": (
                updated_timestamp + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
            ).isoformat(),
            "culled_timestamp": (
                updated_timestamp + timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)
            ).isoformat(),
        }
    }

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.usefixtures("event_datetime_mock")
def test_add_host_with_stale_timestamp_ignore(mq_create_or_update_host):
    """
    Tests to see if the host is successfully created with stale_timestamp
    but ignore it. It should use the default stale_timestamp.
    """
    expected_insights_id = generate_uuid()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=expected_insights_id,
        stale_timestamp="2025-01-01T00:00:00Z",
    )

    host_keys_to_check = ["reporter", "stale_timestamp", "culled_timestamp"]

    key, event, _ = mq_create_or_update_host(host, return_all_data=True)
    updated_timestamp = datetime.fromisoformat(event["host"]["last_check_in"])

    expected_results = {
        "host": {
            **host.data(),
            "stale_timestamp": (updated_timestamp + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)).isoformat(),
            "stale_warning_timestamp": (
                updated_timestamp + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
            ).isoformat(),
            "culled_timestamp": (
                updated_timestamp + timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)
            ).isoformat(),
        }
    }

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


def test_add_host_missing_reporter_field(mocker, mq_create_or_update_host):
    """
    tests to check the API will reject a host if it doesn't have both
    culling fields. This should raise InventoryException.
    """
    field_to_remove = "reporter"
    mock_notification_event_producer = mocker.Mock()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"])
    delattr(host, field_to_remove)

    with pytest.raises(InventoryException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_batch_mq_add_host_operations(mocker, event_producer, flask_app):
    host = minimal_host(
        insights_id=generate_uuid(),
    ).data()

    msg = json.dumps(
        wrap_message(
            host,
            "add_host",
            get_platform_metadata(),
        )
    )

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=7,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
            conventional_time_to_stale_seconds=1,
            conventional_time_to_stale_warning_seconds=1,
            conventional_time_to_delete_seconds=1,
        ),
    )
    write_batch_patch = mocker.patch("app.queue.host_mq.write_message_batch")

    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage(message=msg) for _ in range(5)],
                [FakeMessage(message=msg) for _ in range(3)],
                [FakeMessage(message=msg) for _ in range(4)],
                [],
                [],
                [],
                [],
            ]
        }
    )

    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, mocker.Mock())
    consumer.event_loop(mocker.Mock(side_effect=(False, False, False, True)))

    # 12 messages were sent, but it should have only committed three times:
    # - Once after 7 messages (the batch size)
    # - Once after all messages have been produced
    # - Once after it tries to consume more messages but gets an empty array
    assert write_batch_patch.call_count == 3


@pytest.mark.usefixtures("flask_app")
@pytest.mark.parametrize("identity", (SYSTEM_IDENTITY,))
def test_add_host_logs(identity, mocker, caplog):
    caplog.at_level(logging.INFO)

    expected_insights_id = generate_uuid()
    host = minimal_host(account=identity["account_number"], insights_id=expected_insights_id)

    mock_notification_event_producer = mocker.Mock()

    message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
    consumer = IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mock_notification_event_producer)
    result = consumer.handle_message(json.dumps(message))

    assert result.event_type == EventType.created
    assert str(result.row.insights_id) == expected_insights_id
    add_host_record = next(
        (r for r in caplog.records if getattr(r, "input_host", None) is not None),
        None,
    )
    assert add_host_record is not None, "Expected a log record with extra['input_host']"
    assert add_host_record.input_host["system_profile"] == "{}"
    mock_notification_event_producer.write_event.assert_not_called()


def test_add_host_subman_id(mq_create_or_update_host_subman_id, db_get_host):
    subscription_manager_id = generate_uuid()
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], subscription_manager_id=subscription_manager_id)

    mq_create_or_update_host_subman_id(host)

    record = db_get_host(subscription_manager_id)

    assert str(record.id) == str(subscription_manager_id)


@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_add_host_with_rhsm_payloads_rejected(mocker, mq_create_or_update_host, reporter):
    mocker.patch("app.queue.host_mq.get_flag_value", return_value=True)
    host = minimal_host(insights_id=generate_uuid(), reporter=reporter)
    with pytest.raises(ValidationException) as excinfo:
        mq_create_or_update_host(host)
    assert "RHSM payloads are not currently allowed" in str(excinfo.value)


@pytest.mark.parametrize("reporter", ["puptoo", "satellite", "cloud-connector", "yuptoo"])
def test_add_non_rhsm_host_with_rhsm_payloads_rejected(mocker, mq_create_or_update_host, reporter):
    mocker.patch("app.queue.host_mq.get_flag_value", return_value=True)
    host = minimal_host(insights_id=generate_uuid(), reporter=reporter)
    assert mq_create_or_update_host(host) is not None


@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_add_host_with_rhsm_payloads_allowed_rhsm_payloads_not_rejected(mocker, mq_create_or_update_host, reporter):
    mocker.patch("app.queue.host_mq.get_flag_value", return_value=False)
    host = minimal_host(insights_id=generate_uuid(), reporter=reporter)
    assert mq_create_or_update_host(host) is not None
