import logging
from unittest import mock
from unittest.mock import patch

import pytest
from confluent_kafka import KafkaException

from app.models import Host
from app.queue.event_producer import MessageDetails
from app.queue.event_producer import logger as event_producer_logger
from lib.host_delete import delete_hosts
from lib.host_repository import get_host_list_by_id_list_from_db
from tests.helpers.api_utils import HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.db_utils import db_host
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.mq_utils import assert_delete_notification_is_valid
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


def test_delete_non_existent_host(event_producer_mock, notification_event_producer_mock, api_delete_host):
    host_id = generate_uuid()

    response_status, response_data = api_delete_host(host_id)

    assert_response_status(response_status, expected_status=404)


def test_delete_with_invalid_host_id(api_delete_host):
    host_id = "notauuid"

    response_status, response_data = api_delete_host(host_id)

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

    response_status, response_data = api_delete_host(host.id, query_parameters={"branch_id": "1234"})

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

    response_status, response_data = api_delete_host(host.id, extra_headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, expected_request_id=request_id
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)


def test_create_then_delete_without_request_id(
    event_datetime_mock, event_producer_mock, notification_event_producer_mock, db_create_host, api_delete_host
):
    host = db_create_host()

    response_status, response_data = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock,
        host=host,
        timestamp=event_datetime_mock,
        expected_request_id=None,
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)


def test_create_then_delete_without_insights_id(
    event_datetime_mock, event_producer_mock, notification_event_producer_mock, db_create_host, api_delete_host
):
    host = db_host()
    del host.canonical_facts["insights_id"]

    db_create_host(host=host)

    response_status, response_data = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)


def test_delete_all_hosts(
    event_producer_mock,
    notification_event_producer_mock,
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
    response_status, response_data = api_delete_all_hosts({})

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

    response_status, response_data = api_delete_host(host.id, extra_headers=headers)

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
    response_status, response_data = api_delete_host(host.id)

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
    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=404)

    assert event_producer_mock.event is None
    assert notification_event_producer_mock.event is None


def test_delete_when_some_hosts_is_deleted(
    event_producer_mock, notification_event_producer_mock, db_create_multiple_hosts, api_delete_host, mocker
):
    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(hosts[0].id), str(hosts[1].id)]

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock(host_id_list[0:1]))

    # Two hosts queried, one of them deleted by a different process. Only one event emitted,
    # returning 200 OK.
    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=200)

    assert host_id_list[1] == event_producer_mock.key


def test_delete_host_with_RBAC_allowed(
    subtests,
    mocker,
    api_delete_host,
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_host,
    db_create_host,
    enable_rbac,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            response_status, response_data = api_delete_host(host.id)

            assert_response_status(response_status, 200)

            assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

            assert_delete_notification_is_valid(
                notification_event_producer=notification_event_producer_mock, host=host
            )

            assert not db_get_host(host.id)


def test_delete_host_with_RBAC_denied(
    subtests,
    mocker,
    api_delete_host,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    enable_rbac,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            response_status, response_data = api_delete_host(host.id)

            assert_response_status(response_status, 403)

            assert db_get_host(host.id)


def test_delete_host_with_RBAC_bypassed_as_system(
    api_delete_host,
    event_datetime_mock,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_host,
    db_create_host,
    enable_rbac,
):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    response_status, response_data = api_delete_host(host.id, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, identity=SYSTEM_IDENTITY
    )

    assert_delete_notification_is_valid(notification_event_producer=notification_event_producer_mock, host=host)

    assert not db_get_host(host.id)


def test_delete_hosts_chunk_size(
    event_producer_mock,
    notification_event_producer_mock,
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


def test_delete_host_that_belongs_to_group_success(
    event_producer_mock,
    notification_event_producer_mock,
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


def test_delete_host_that_belongs_to_group_fail(
    event_producer_mock,
    notification_event_producer_mock,
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
    deleted_by_this_query_mock = mocker.patch("lib.host_delete._deleted_by_this_query")
    deleted_by_this_query_mock.side_effect = InterruptedError()

    # Delete the first host
    api_delete_host(host_id_list[0])

    # Confirm that the group contains all 3 hosts
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 3
    assert host_id_list[0] in [host.id for host in hosts_after]


def test_delete_host_RBAC_allowed_specific_groups(
    mocker,
    db_create_group,
    db_create_host_group_assoc,
    api_delete_host,
    db_create_host,
    db_get_hosts_for_group,
    enable_rbac,
    event_producer_mock,
    notification_event_producer_mock,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    host_id = db_create_host().id
    group_id = db_create_group("test_test").id
    db_create_host_group_assoc(host_id, group_id)

    # Make a list of allowed group IDs (including some mock ones)
    group_id_list = [generate_uuid(), str(group_id), generate_uuid()]

    # Grant permissions to all 3 groups
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = group_id_list
    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, _ = api_delete_host(host_id)

    # Should be allowed
    assert_response_status(response_status, 200)
    # Group should now have 0 hosts
    assert len(db_get_hosts_for_group(group_id)) == 0


def test_delete_host_RBAC_denied_specific_groups(
    mocker, db_create_host, db_get_host, api_delete_host, enable_rbac, event_producer_mock
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    host_id = db_create_host().id

    # Deny access to created group
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [generate_uuid(), generate_uuid()]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, _ = api_delete_host(host_id)

    # If the user doesn't have access to the group, the host can't be found. Should this be 404 or 403?
    assert_response_status(response_status, expected_status=404)

    assert db_get_host(host_id)


def test_postgres_delete_filtered_hosts(
    db_create_host, api_get, api_delete_filtered_hosts, event_producer_mock, notification_event_producer_mock
):
    host_1_id = db_create_host(extra_data={"display_name": "foobar"}).id
    host_2_id = db_create_host(extra_data={"display_name": "foobaz"}).id

    # Create another host that we don't want to be deleted
    not_deleted_host_id = str(db_create_host(extra_data={"canonical_facts": {"insights_id": generate_uuid()}}).id)

    with patch("api.host.get_flag_value", return_value=True):
        # Delete the first two hosts using the bulk deletion endpoint
        response_status, response_data = api_delete_filtered_hosts({"hostname_or_id": "foo"})
        assert_response_status(response_status, expected_status=202)
        assert response_data["hosts_deleted"] == 2

        # Make sure they were both deleted and produced deletion events
        assert '"type": "delete"' in event_producer_mock.event
        _, response_data = api_get(build_hosts_url(host_1_id))
        assert len(response_data["results"]) == 0
        _, response_data = api_get(build_hosts_url(host_2_id))
        assert len(response_data["results"]) == 0

        # Make sure the other host wasn't deleted
        response_status, response_data = api_get(build_hosts_url(not_deleted_host_id))
        assert_response_status(response_status, expected_status=200)
        assert response_data["results"][0]["id"] == not_deleted_host_id


def test_postgres_delete_filtered_hosts_nomatch(
    db_create_host, api_get, api_delete_filtered_hosts, event_producer_mock
):
    # Create a host that we don't want to be deleted
    not_deleted_host_id = str(db_create_host(extra_data={"canonical_facts": {"insights_id": generate_uuid()}}).id)

    with patch("api.host.get_flag_value", return_value=True):
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
    assert caplog.records[0].system_profile == "{}"


def test_delete_with_ui_host(
    db_create_host, api_delete_host, event_datetime_mock, event_producer_mock, notification_event_producer_mock
):
    host = db_create_host(extra_data={"canonical_facts": {"subscription_manager_id": generate_uuid()}})
    headers = {"x-rh-frontend-origin": "hcc"}

    response_status, _ = api_delete_host(host.id, extra_headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, manual_delete=True
    )


class DeleteHostsMock:
    @classmethod
    def create_mock(cls, hosts_ids_to_delete, manual_delete=False):
        def _constructor(
            select_query,
            event_producer,
            notification_event_producer,
            chunk_size,
            identity=None,
            control_rule=None,
            manual_delete=manual_delete,
        ):
            return cls(
                hosts_ids_to_delete,
                select_query,
                event_producer,
                notification_event_producer,
                chunk_size,
                identity=identity,
                control_rule=control_rule,
                manual_delete=manual_delete,
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
        manual_delete=False,
    ):
        self.host_ids_to_delete = host_ids_to_delete
        self.original_query = delete_hosts(
            original_query,
            event_producer,
            notification_event_producer,
            chunk_size,
            identity=identity,
            control_rule=control_rule,
            manual_delete=manual_delete,
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


class DeleteQueryWrapper:
    def __init__(self, mocker):
        self.query = None
        self.mocker = mocker

    def mock_get_host_list_by_id_list(self, host_id_list, rbac_filter=None):
        self.query = get_host_list_by_id_list_from_db(host_id_list, rbac_filter)
        self.query.limit = self.mocker.Mock(wraps=self.query.limit)
        return self.query
