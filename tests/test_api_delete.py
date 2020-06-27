#!/usr/bin/env python
from app.models import Host
from lib.host_delete import delete_hosts
from tests.utils import generate_uuid
from tests.utils.api_utils import assert_response_status
from tests.utils.mq_utils import assert_delete_event_is_valid


def test_delete_non_existent_host(api_delete_host):
    host_id = generate_uuid()

    response_status, response_data = api_delete_host(host_id)

    assert_response_status(response_status, expected_status=404)


def test_delete_with_invalid_host_id(api_delete_host):
    host_id = "notauuid"

    response_status, response_data = api_delete_host(host_id)

    assert_response_status(response_status, expected_status=400)


def test_create_then_delete(event_datetime_mock, event_producer_mock, db_create_host, db_get_host, api_delete_host):
    host = db_create_host()

    response_status, response_data = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

    assert not db_get_host(host.id)


def test_create_then_delete_with_branch_id(
    event_datetime_mock, event_producer_mock, db_create_host, db_get_host, api_delete_host
):
    host = db_create_host()

    response_status, response_data = api_delete_host(host.id, query_parameters={"branch_id": "1234"})

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

    assert not db_get_host(host.id)


def test_create_then_delete_with_request_id(event_datetime_mock, event_producer_mock, db_create_host, api_delete_host):
    host = db_create_host()

    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    response_status, response_data = api_delete_host(host.id, headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, expected_request_id=request_id
    )


def test_create_then_delete_without_request_id(
    event_datetime_mock, event_producer_mock, db_create_host, api_delete_host
):
    host = db_create_host()

    response_status, response_data = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock, expected_request_id="-1"
    )


def test_create_then_delete_check_metadata(event_datetime_mock, event_producer_mock, db_create_host, api_delete_host):
    host = db_create_host()

    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    response_status, response_data = api_delete_host(host.id, headers=headers)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(
        event_producer=event_producer_mock,
        host=host,
        timestamp=event_datetime_mock,
        expected_request_id=request_id,
        expected_metadata={"request_id": request_id},
    )


def test_delete_when_one_host_is_deleted(event_producer_mock, db_create_host, api_delete_host, mocker):
    host = db_create_host()

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock([host.id]))

    # One host queried, but deleted by a different process. No event emitted yet returning
    # 200 OK.
    response_status, response_data = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert event_producer_mock.event is None


def test_delete_when_all_hosts_are_deleted(event_producer_mock, db_create_multiple_hosts, api_delete_host, mocker):
    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(hosts[0].id), str(hosts[1].id)]

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock(host_id_list))

    # Two hosts queried, but both deleted by a different process. No event emitted yet
    # returning 200 OK.
    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=200)

    assert event_producer_mock.event is None


def test_delete_when_some_hosts_is_deleted(event_producer_mock, db_create_multiple_hosts, api_delete_host, mocker):
    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(hosts[0].id), str(hosts[1].id)]

    mocker.patch("api.host.delete_hosts", DeleteHostsMock.create_mock(host_id_list[0:1]))

    # Two hosts queried, one of them deleted by a different process. Only one event emitted,
    # returning 200 OK.
    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=200)

    assert host_id_list[1] == event_producer_mock.key


class DeleteHostsMock:
    @classmethod
    def create_mock(cls, hosts_ids_to_delete):
        def _constructor(select_query, event_producer):
            return cls(hosts_ids_to_delete, select_query, event_producer)

        return _constructor

    def __init__(self, host_ids_to_delete, original_query, event_producer):
        self.host_ids_to_delete = host_ids_to_delete
        self.original_query = delete_hosts(original_query, event_producer)

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
