from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from typing import Any
from unittest import mock
from unittest.mock import patch

import pytest
from confluent_kafka import KafkaException

from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Host
from app.queue.event_producer import MessageDetails
from app.queue.event_producer import logger as event_producer_logger
from lib.host_delete import delete_hosts
from lib.host_repository import get_host_list_by_id_list_from_db
from tests.helpers.api_utils import HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import create_custom_rbac_response
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.db_utils import db_host
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.mq_utils import assert_delete_notification_is_valid
from tests.helpers.test_utils import RHSM_ERRATA_IDENTITY_PROD
from tests.helpers.test_utils import RHSM_ERRATA_IDENTITY_STAGE
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_non_existent_host(api_delete_host):
    host_id = generate_uuid()

    response_status, _ = api_delete_host(host_id)

    assert_response_status(response_status, expected_status=404)


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_non_existent_host_response_includes_missing_ids(api_delete_host):
    # Verify that 404 response includes the not_found_ids field
    host_id = generate_uuid()

    response_status, response_data = api_delete_host(host_id)

    assert_response_status(response_status, expected_status=404)
    assert "not_found_ids" in response_data
    assert response_data["not_found_ids"] == [host_id]
    assert response_data["detail"] == "One or more hosts not found."


def test_delete_with_missing_host_id_and_valid_host_id(db_create_host, api_delete_host, db_get_host):
    # Attempt to simultaneously delete a real host and a missing host
    valid_host_id = db_create_host().id
    missing_host_id = generate_uuid()
    response_status, _ = api_delete_host(f"{str(valid_host_id)},{str(missing_host_id)}")

    assert_response_status(response_status, expected_status=404)

    # Make sure a partial deletion did not occur
    assert db_get_host(valid_host_id)


def test_delete_with_missing_host_id_response_includes_only_missing_ids(db_create_host, api_delete_host, db_get_host):
    # Verify 404 response only includes the missing ID, not the valid one
    valid_host_id = str(db_create_host().id)
    missing_host_id = generate_uuid()

    response_status, response_data = api_delete_host(f"{valid_host_id},{missing_host_id}")

    assert_response_status(response_status, expected_status=404)
    assert "not_found_ids" in response_data
    assert response_data["not_found_ids"] == [missing_host_id]
    assert valid_host_id not in response_data["not_found_ids"]

    # Make sure a partial deletion did not occur
    assert db_get_host(valid_host_id)


def test_delete_with_invalid_host_id(api_delete_host):
    host_id = "notauuid"

    response_status, _ = api_delete_host(host_id)

    assert_response_status(response_status, expected_status=400)


def test_create_then_delete(
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    api_delete_host,
):
    host = db_create_host()

    response_status, _ = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)
    assert_delete_notification_is_valid(
        notification_event_producer=notification_event_producer_mock,
        host=host,
    )

    assert not db_get_host(host.id)


def test_create_then_delete_with_branch_id(
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    api_delete_host,
):
    host = db_create_host()

    response_status, _ = api_delete_host(host.id, query_parameters={"branch_id": "1234"})

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)

    assert not db_get_host(host.id)


def test_create_then_delete_with_request_id(
    event_datetime_mock, event_producer_mock, notification_event_producer_mock, db_create_host, api_delete_host
):
    host = db_create_host(extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}})

    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    response_status, _ = api_delete_host(host.id, extra_headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, expected_request_id=request_id
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)


def test_create_then_delete_without_request_id(
    event_datetime_mock, event_producer_mock, notification_event_producer_mock, db_create_host, api_delete_host
):
    host = db_create_host()

    response_status, _ = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock,
        host=host,
        timestamp=event_datetime_mock,
        expected_request_id=None,
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_create_then_delete_without_insights_id(
    event_datetime_mock, event_producer_mock, db_create_host, api_delete_host
):
    host = db_host()
    del host.insights_id

    db_create_host(host=host)

    response_status, _ = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_delete_hosts_filtered_by_subscription_manager_id(
    db_create_host,
    api_delete_filtered_hosts,
    event_datetime_mock,
    event_producer_mock,
):
    db_create_host(host=db_host())
    host = db_create_host(host=db_host())
    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"subscription_manager_id": host.subscription_manager_id}
    )
    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1
    assert_response_status(response_status, expected_status=202)
    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)


@pytest.mark.parametrize(
    "host_type,system_type,nomatch_host_type",
    (
        (None, "conventional", "edge"),
        ("edge", "edge", "cluster"),
        ("cluster", "cluster", "edge"),
    ),
)
@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_hosts_filtered_by_system_type(
    host_type,
    system_type,
    nomatch_host_type,
    mq_create_or_update_host,
    db_get_host,
    api_delete_filtered_hosts,
):
    host_to_keep_id = mq_create_or_update_host(
        minimal_host(system_profile={"host_type": nomatch_host_type} if nomatch_host_type else {})
    ).id
    host_to_delete_id = mq_create_or_update_host(
        minimal_host(system_profile={"host_type": host_type} if host_type else {})
    ).id

    response_status, response_data = api_delete_filtered_hosts(query_parameters={"system_type": system_type})

    assert response_data["hosts_found"] == 1
    assert response_data["hosts_deleted"] == 1
    assert_response_status(response_status, expected_status=202)

    # Check that the host to delete was deleted and the host to keep was not
    assert not db_get_host(host_to_delete_id)
    assert db_get_host(host_to_keep_id)


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_delete_all_hosts(
    event_producer_mock,
    db_create_multiple_hosts,
    db_get_hosts,
    api_delete_all_hosts,
):
    created_hosts = db_create_multiple_hosts(how_many=5)
    host_ids = [str(host.id) for host in created_hosts]

    # delete all hosts on the current org_id
    response_status, response_data = api_delete_all_hosts({"confirm_delete_all": True})

    assert '"type": "delete"' in event_producer_mock.event
    assert response_data.get("hosts_deleted") == len(created_hosts)
    assert_response_status(response_status, expected_status=202)
    assert len(host_ids) == response_data["hosts_deleted"]

    # check db for the deleted hosts using their IDs
    host_id_list = [str(host.id) for host in created_hosts]
    deleted_hosts = db_get_hosts(host_id_list)
    assert deleted_hosts.count() == 0


def test_delete_all_hosts_with_missing_required_params(api_delete_all_hosts, event_producer_mock):
    # delete all hosts using incomplete filter
    response_status, _ = api_delete_all_hosts({})

    assert_response_status(response_status, expected_status=400)
    assert event_producer_mock.event is None


def test_create_then_delete_check_metadata(
    event_datetime_mock, event_producer_mock, notification_event_producer_mock, db_create_host, api_delete_host
):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    response_status, _ = api_delete_host(host.id, extra_headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock,
        host=host,
        timestamp=event_datetime_mock,
        expected_request_id=request_id,
        expected_metadata={"request_id": request_id},
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)


def test_delete_when_one_host_is_deleted(
    event_producer_mock, notification_event_producer_mock, db_create_host, api_delete_host, mocker
):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock([host.id]))

    # One host queried, but deleted by a different process. No event emitted yet returning
    # 200 OK.
    response_status, _ = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=404)

    assert event_producer_mock.event is None
    assert notification_event_producer_mock.event is None


def test_delete_when_all_hosts_are_deleted(
    event_producer_mock, notification_event_producer_mock, db_create_multiple_hosts, api_delete_host, mocker
):
    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(hosts[0].id), str(hosts[1].id)]

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock(host_id_list))

    # Two hosts queried, but both deleted by a different process. No event emitted yet
    # returning 200 OK.
    response_status, _ = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=404)

    assert event_producer_mock.event is None
    assert notification_event_producer_mock.event is None


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_delete_when_some_hosts_is_deleted(event_producer_mock, db_create_multiple_hosts, api_delete_host, mocker):
    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(hosts[0].id), str(hosts[1].id)]

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock(host_id_list[0:1]))

    # Two hosts queried, one of them deleted by a different process. Only one event emitted,
    # returning 200 OK.
    response_status, _ = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=200)

    assert host_id_list[1] == event_producer_mock.key


@pytest.mark.usefixtures("enable_rbac")
def test_delete_host_with_RBAC_allowed(
    subtests,
    mocker,
    api_delete_host,
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_host,
    db_create_host,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            response_status, _ = api_delete_host(host.id)

            assert_response_status(response_status, 200)

            assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

            assert_delete_notification_is_valid(
                notification_event_producer=notification_event_producer_mock, host=host
            )

            assert not db_get_host(host.id)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_host_with_RBAC_denied(
    subtests,
    mocker,
    api_delete_host,
    db_create_host,
    db_get_host,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            response_status, _ = api_delete_host(host.id)

            assert_response_status(response_status, 403)

            assert db_get_host(host.id)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_host_with_RBAC_bypassed_as_system(
    api_delete_host,
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_host,
    db_create_host,
):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    response_status, _ = api_delete_host(host.id, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, identity=SYSTEM_IDENTITY
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)

    assert not db_get_host(host.id)


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_hosts_chunk_size(
    db_create_multiple_hosts,
    api_delete_host,
    mocker,
    inventory_config,
):
    inventory_config.host_delete_chunk_size = 5

    query_wrapper = DeleteQueryWrapper(mocker)
    mocker.patch("api.host.get_host_list_by_id_list_from_db", query_wrapper.mock_get_host_list_by_id_list)

    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(host.id) for host in hosts]

    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=200)

    query_wrapper.query.limit.assert_called_with(5)


@pytest.mark.parametrize("send_side_effects", ((mock.Mock(), KafkaException()), (mock.Mock(), KafkaException("oops"))))
def test_delete_stops_after_kafka_exception(
    mocker,
    send_side_effects,
    event_producer,
    notification_event_producer,
    db_create_multiple_hosts,
    api_delete_host,
    db_get_hosts,
    inventory_config,
):
    mocker.patch("lib.host_delete.kafka_available")
    inventory_config.host_delete_chunk_size = 1
    hosts = db_create_multiple_hosts(how_many=3)
    host_id_list = [str(host.id) for host in hosts]

    event_producer._kafka_producer.produce.side_effect = send_side_effects

    response_status, _ = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=500)

    remaining_hosts = db_get_hosts(host_id_list)
    assert remaining_hosts.count() == 2
    assert event_producer._kafka_producer.produce.call_count == 2
    assert notification_event_producer._kafka_producer.produce.call_count == 1


def test_delete_with_callback_receiving_error(
    mocker,
    event_producer,
    notification_event_producer,
    db_create_host,
    api_delete_host,
    db_get_hosts,
):
    mocker.patch("lib.host_delete.kafka_available")
    host = db_create_host()
    headers = mock.MagicMock()
    event = mock.MagicMock()
    message = None  # message is only sent when message is too long to be produced
    error = mock.MagicMock()
    message_not_produced_mock = mocker.patch("app.queue.event_producer.message_not_produced")

    msgdet = MessageDetails(topic=None, event=event, headers=headers, key=host.id)
    event_producer._kafka_producer.produce.side_effects = msgdet.on_delivered(error, message)

    response_status, _ = api_delete_host(",".join([str(host.id)]))

    assert_response_status(response_status, expected_status=200)

    remaining_hosts = db_get_hosts([host.id])

    assert remaining_hosts.count() == 0
    assert event_producer._kafka_producer.produce.call_count == 1
    assert notification_event_producer._kafka_producer.produce.call_count == 1
    message_not_produced_mock.assert_called_once_with(
        event_producer_logger, error, None, event, host.id, headers, message
    )


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_host_that_belongs_to_group_success(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_delete_host,
):
    # If successful, the host should be removed from the group,
    # and then deleted in the same transaction.

    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    # Add all 3 hosts to the group
    for host_id in host_id_list:
        db_create_host_group_assoc(host_id, group_id)

    # Confirm that the associations exist
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 3

    # Delete the first host
    response_status, _ = api_delete_host(host_id_list[0])
    assert response_status == 200

    # Confirm that the group does not contain the first host
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 2
    assert host_id_list[0] not in [host.id for host in hosts_after]


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_host_that_belongs_to_group_fail(
    mocker,
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_delete_host,
):
    # If something goes wrong, the whole thing should roll back,
    # and the host should still be a part of the group.

    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    # Add all 3 hosts to the group
    for host_id in host_id_list:
        db_create_host_group_assoc(host_id, group_id)

    # Confirm that the associations exist
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 3

    # Patch it so the DB deletion fails
    deleted_by_this_query_mock = mocker.patch("lib.host_delete.deleted_by_this_query")
    deleted_by_this_query_mock.side_effect = InterruptedError()

    # Delete the first host
    api_delete_host(host_id_list[0])

    # Confirm that the group contains at least 2 hosts, as the first host is deleted before
    # the kafka event is produced.
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 3
    assert host_id_list[0] in [host.id for host in hosts_after]


@pytest.mark.usefixtures("enable_rbac", "event_producer_mock", "notification_event_producer_mock")
def test_delete_host_RBAC_allowed_specific_groups(
    mocker,
    db_create_group,
    db_create_host_group_assoc,
    api_delete_host,
    db_create_host,
    db_get_hosts_for_group,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    host_id = db_create_host().id
    group_id = db_create_group("test_test").id
    db_create_host_group_assoc(host_id, group_id)

    # Make a list of allowed group IDs (including some mock ones)
    group_id_list = [generate_uuid(), str(group_id), generate_uuid()]

    # Grant permissions to all 3 groups
    get_rbac_permissions_mock.return_value = create_custom_rbac_response(
        group_id_list, RBACFilterOperation.IN, "write"
    )

    response_status, _ = api_delete_host(host_id)

    # Should be allowed
    assert_response_status(response_status, 200)
    # Group should now have 0 hosts
    assert len(db_get_hosts_for_group(group_id)) == 0


@pytest.mark.usefixtures("enable_rbac", "event_producer_mock")
def test_delete_host_RBAC_denied_specific_groups(mocker, db_create_host, db_get_host, api_delete_host):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    host_id = db_create_host().id

    # Deny access to our created group, only allow access to some mock groups
    get_rbac_permissions_mock.return_value = create_custom_rbac_response(
        [generate_uuid(), generate_uuid()], RBACFilterOperation.IN, "write"
    )

    response_status, _ = api_delete_host(host_id)

    # If the user doesn't have access to the group, the host can't be found. Should this be 404 or 403?
    assert_response_status(response_status, expected_status=404)

    assert db_get_host(host_id)


@pytest.mark.usefixtures("notification_event_producer_mock")
@pytest.mark.parametrize(
    "request_body",
    (
        {"hostname_or_id": "foo"},
        {"registered_with": "satellite"},
    ),
)
def test_postgres_delete_filtered_hosts(
    db_create_host, api_get, request_body, api_delete_filtered_hosts, event_producer_mock
):
    host_1_id = db_create_host(extra_data={"display_name": "foobar", "reporter": "satellite"}).id
    host_2_id = db_create_host(extra_data={"display_name": "foobaz", "reporter": "satellite"}).id
    host_3_id = db_create_host(extra_data={"display_name": "asdf", "reporter": "puptoo"}).id

    # Create another host that we don't want to be deleted
    not_deleted_host_id = str(db_create_host(extra_data={"insights_id": generate_uuid()}).id)

    # Delete the first two hosts using the bulk deletion endpoint
    response_status, response_data = api_delete_filtered_hosts(request_body)
    assert_response_status(response_status, expected_status=202)
    assert response_data["hosts_deleted"] == 2

    # Make sure they were both deleted and produced deletion events
    assert '"type": "delete"' in event_producer_mock.event
    response_status, _ = api_get(build_hosts_url(host_1_id))
    assert response_status == 404
    response_status, _ = api_get(build_hosts_url(host_2_id))
    assert response_status == 404
    _, response_data = api_get(build_hosts_url(host_3_id))
    assert len(response_data["results"]) == 1

    # Make sure the other host wasn't deleted
    response_status, response_data = api_get(build_hosts_url(not_deleted_host_id))
    assert_response_status(response_status, expected_status=200)
    assert response_data["results"][0]["id"] == not_deleted_host_id


@pytest.mark.usefixtures("notification_event_producer_mock")
@pytest.mark.parametrize("identity", (RHSM_ERRATA_IDENTITY_PROD, RHSM_ERRATA_IDENTITY_STAGE), ids=("prod", "stage"))
def test_delete_hosts_by_subman_id_internal_rhsm_request(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    event_producer_mock: MockEventProducer,
    identity: dict[str, Any],
):
    """
    This test simulates the internal `DELETE /hosts?subscription_manager_id=...` request from RHSM
    that they make when a host is unregistered from RHSM, to delete it from Insights Inventory.
    """
    searched_subman_id = generate_uuid()
    matching_host_id = str(db_create_host(extra_data={"subscription_manager_id": searched_subman_id}).id)
    not_matching_host_id = str(db_create_host(extra_data={"subscription_manager_id": generate_uuid()}).id)
    different_org_host_id = str(
        db_create_host(extra_data={"subscription_manager_id": searched_subman_id, "org_id": "12345"}).id
    )

    # Delete the host using the bulk deletion endpoint
    response_status, response_data = api_delete_filtered_hosts(
        {"subscription_manager_id": searched_subman_id},
        identity=identity,
        extra_headers={"x-inventory-org-id": "test"},
    )
    assert_response_status(response_status, expected_status=202)
    assert response_data["hosts_deleted"] == 1
    assert response_data["hosts_found"] == 1

    # Make sure the correct host was deleted and produced a deletion event
    assert '"type": "delete"' in event_producer_mock.event

    response_status, _ = api_get(build_hosts_url([matching_host_id, not_matching_host_id, different_org_host_id]))
    assert response_status == 404

    _, response_data = api_get(build_hosts_url([not_matching_host_id]))
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == not_matching_host_id

    # Make sure the host from different org wasn't deleted
    different_org_identity = deepcopy(USER_IDENTITY)
    different_org_identity["org_id"] = "12345"
    _, response_data = api_get(
        build_hosts_url([different_org_host_id]),
        identity=different_org_identity,
    )
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == different_org_host_id


@pytest.mark.usefixtures("event_producer_mock")
def test_postgres_delete_filtered_hosts_nomatch(db_create_host, api_get, api_delete_filtered_hosts):
    # Create a host that we don't want to be deleted
    not_deleted_host_id = str(db_create_host(extra_data={"insights_id": generate_uuid()}).id)

    # Call the delete endpoint when no hosts match the criteria
    response_status, response_data = api_delete_filtered_hosts({"insights_id": generate_uuid()})
    assert response_data["hosts_found"] == 0
    assert response_data["hosts_deleted"] == 0

    # Make sure the existing host wasn't deleted
    response_status, response_data = api_get(build_hosts_url(not_deleted_host_id))
    assert_response_status(response_status, expected_status=200)
    assert response_data["results"][0]["id"] == not_deleted_host_id


def test_log_create_delete(
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    api_delete_host,
    caplog,
):
    caplog.at_level(logging.INFO)
    host = db_create_host()

    response_status, _ = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)
    assert_delete_notification_is_valid(
        notification_event_producer=notification_event_producer_mock,
        host=host,
    )

    assert not db_get_host(host.id)
    # The use of logger.info() logs more messages before the deleted_host message
    # Find the first log record that has the system_profile attribute
    deleted_host_record = next((r for r in caplog.records if hasattr(r, "system_profile")), None)
    assert deleted_host_record is not None, "Could not find deleted_host log record"
    assert deleted_host_record.system_profile == "{}"


@pytest.mark.usefixtures("notification_event_producer_mock")
def test_delete_with_ui_host(db_create_host, api_delete_host, event_datetime_mock, event_producer_mock):
    host = db_create_host(extra_data={"subscription_manager_id": generate_uuid()})
    headers = {"x-rh-frontend-origin": "hcc"}

    response_status, _ = api_delete_host(host.id, extra_headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, initiated_by_frontend=True
    )


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_delete_hosts_filter_last_check_in_both_same(db_create_host, db_get_host, api_delete_filtered_hosts):
    match_host = db_create_host()
    match_host_id = str(match_host.id)
    nomatch_host_id = str(db_create_host().id)
    response_status, _ = api_delete_filtered_hosts(
        query_parameters={
            "last_check_in_start": match_host.last_check_in,
            "last_check_in_end": match_host.last_check_in,
        }
    )
    assert response_status == 202
    assert not db_get_host(match_host_id)
    assert db_get_host(nomatch_host_id)


def test_delete_hosts_filter_last_check_in_invalid_format(api_delete_filtered_hosts, subtests):
    invalid_formats = ("foobar", "{}", "[]", generate_uuid(), [datetime.now(), datetime.now() - timedelta(days=7)])
    for invalid_format in invalid_formats:
        for param in ("last_check_in_start", "last_check_in_end"):
            with subtests.test(invalid_format=invalid_format, param=param):
                response_status, response_data = api_delete_filtered_hosts(
                    query_parameters={param: str(invalid_format)}
                )
                assert response_status == 400
                assert "is not a 'date-time'" in response_data["detail"]


@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_delete_hosts_filter_updated_last_check_in_start_after_end(api_delete_filtered_hosts, param_prefix):
    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={
            f"{param_prefix}_start": datetime.now(),
            f"{param_prefix}_end": datetime.now() - timedelta(days=1),
        }
    )
    assert response_status == 400
    assert f"{param_prefix}_start cannot be after {param_prefix}_end." in response_data["detail"]


class DeleteHostsMock:
    @classmethod
    def create_mock(cls, hosts_ids_to_delete, initiated_by_frontend=False):
        def _constructor(
            select_query,
            event_producer,
            notification_event_producer,
            chunk_size,
            identity=None,
            control_rule=None,
            initiated_by_frontend=initiated_by_frontend,
        ):
            return cls(
                hosts_ids_to_delete,
                select_query,
                event_producer,
                notification_event_producer,
                chunk_size,
                identity=identity,
                control_rule=control_rule,
                initiated_by_frontend=initiated_by_frontend,
            )

        return _constructor

    def __init__(
        self,
        host_ids_to_delete,
        original_query,
        event_producer,
        notification_event_producer,
        chunk_size,
        identity=None,
        control_rule=None,
        initiated_by_frontend=False,
    ):
        self.host_ids_to_delete = host_ids_to_delete
        self.original_query = delete_hosts(
            original_query,
            event_producer,
            notification_event_producer,
            chunk_size,
            identity=identity,
            control_rule=control_rule,
            initiated_by_frontend=initiated_by_frontend,
        )

    def __getattr__(self, item):
        """
        Forwards all calls to the original query, only intercepting the actual SELECT.
        """
        return getattr(self.original_query, item)

    def _delete_hosts(self):
        delete_query = Host.query.filter(Host.id.in_(self.host_ids_to_delete))
        delete_query.delete(synchronize_session=False)
        delete_query.session.commit()

    def __iter__(self, *args, **kwargs):
        """
        Intercepts the actual SELECT by first running the query and then deleting the hosts,
        causing the race condition.
        """
        iterator = self.original_query.__iter__(*args, **kwargs)
        self._delete_hosts()
        return iterator


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_attempt_delete_host_read_only(api_delete_host):
    with patch("lib.middleware.get_flag_value", return_value=True):
        response_status, _ = api_delete_host(generate_uuid())
        assert_response_status(response_status, expected_status=503)


class DeleteQueryWrapper:
    def __init__(self, mocker):
        self.query = None
        self.mocker = mocker

    def mock_get_host_list_by_id_list(self, host_id_list, identity, rbac_filter=None):
        self.query = get_host_list_by_id_list_from_db(host_id_list, identity, rbac_filter)
        self.query.limit = self.mocker.Mock(wraps=self.query.limit)
        return self.query


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
@pytest.mark.parametrize(
    "staleness_filter",
    [
        ["fresh"],
        ["stale"],
        ["stale_warning"],
        ["fresh", "stale"],
        ["fresh", "stale_warning"],
        ["stale", "stale_warning"],
        ["fresh", "stale", "stale_warning"],
    ],
    ids=lambda param: ",".join(param),
)
@pytest.mark.parametrize("host_type", ("conventional", "edge"))
def test_delete_hosts_filtered_by_staleness(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[..., Host | None],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    mocker: Any,
    staleness_filter: list[str],
    host_type: str,
):
    """
    Test DELETE on /hosts endpoint with 'staleness' parameter.
    This test creates hosts in different staleness states and verifies that
    only hosts matching the staleness filter are deleted.
    """
    secondary_org_id = "12345"

    # Create timestamps for each staleness state (matching the logic in test_api_hosts_get.py)
    staleness_timestamps = {
        "fresh": now(),
        "stale": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS),
        "stale_warning": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS),
    }

    # Create a host in each staleness state
    host_ids_to_delete = []
    host_ids_to_keep = []
    different_org_host_ids = []
    for staleness_state, last_check_in_timestamp in staleness_timestamps.items():
        # Patch the "now" function so the hosts are created in the desired state
        with mocker.patch("app.models.utils.datetime", **{"now.return_value": last_check_in_timestamp}):
            system_profile_facts = {"host_type": host_type} if host_type == "edge" else {}
            host_id = str(db_create_host(extra_data={"system_profile_facts": system_profile_facts}).id)

            # Determine if the host should be deleted based on the filter
            if staleness_state in staleness_filter:
                host_ids_to_delete.append(host_id)
            else:
                host_ids_to_keep.append(host_id)

            # Create a host in a different organization
            different_org_host_ids.append(
                str(
                    db_create_host(
                        extra_data={"system_profile_facts": system_profile_facts, "org_id": secondary_org_id}
                    ).id
                )
            )

    # Execute the delete operation
    response_status, response_data = api_delete_filtered_hosts(query_parameters={"staleness": staleness_filter})
    assert response_status == 202
    assert response_data["hosts_found"] == len(host_ids_to_delete)
    assert response_data["hosts_deleted"] == len(host_ids_to_delete)

    # Verify that the correct hosts were deleted
    for host_id in host_ids_to_delete:
        assert not db_get_host(host_id), f"Host {host_id} should have been deleted"

    # Verify that the other hosts were not deleted
    for host_id in host_ids_to_keep:
        assert db_get_host(host_id), f"Host {host_id} should not have been deleted"

    # Verify that the hosts in the different organization were not deleted
    for host_id in different_org_host_ids:
        assert db_get_host(host_id, org_id=secondary_org_id), f"Host {host_id} should not have been deleted"


@pytest.mark.usefixtures("notification_event_producer_mock", "event_producer_mock")
def test_delete_hosts_filtered_default_staleness(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[..., Host | None],
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    mocker: Any,
):
    """
    Test default staleness on DELETE /hosts endpoint.
    When no staleness filter is provided, the default is to delete fresh, stale, and stale_warning hosts.
    """
    # Create timestamps for each staleness state
    staleness_timestamps = {
        "fresh": now(),
        "stale": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS),
        "stale_warning": now() - timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS),
    }

    # Create hosts for each staleness state with reporter="puptoo"
    host_ids = []
    for last_check_in_timestamp in staleness_timestamps.values():
        with mocker.patch("app.models.utils.datetime", **{"now.return_value": last_check_in_timestamp}):
            host = db_create_host(extra_data={"reporter": "puptoo"})
            host_ids.append(str(host.id))

    # Delete hosts filtered by registered_with="puptoo" without specifying staleness
    # This should use the default staleness filter (all non-culled states)
    response_status, response_data = api_delete_filtered_hosts(query_parameters={"registered_with": "puptoo"})
    assert response_status == 202
    # With default staleness, all three hosts should be deleted (fresh, stale, and stale_warning)
    assert response_data["hosts_deleted"] == len(host_ids)

    # Verify that all hosts were deleted
    for host_id in host_ids:
        assert not db_get_host(host_id), f"Host {host_id} should have been deleted"
