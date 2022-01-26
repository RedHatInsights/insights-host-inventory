from copy import deepcopy
from unittest import mock

import pytest
from kafka.errors import KafkaError

from api.host import _get_host_list_by_id_list
from app.models import Host
from lib.host_delete import delete_hosts
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.db_utils import db_host
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE_FOR_FILTERING
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import SYSTEM_IDENTITY


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
    host = db_create_host(extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}})

    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    response_status, response_data = api_delete_host(host.id, extra_headers=headers)

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


def test_create_then_delete_without_insights_id(
    event_datetime_mock, event_producer_mock, db_create_host, api_delete_host
):
    host = db_host()
    del host.canonical_facts["insights_id"]

    db_create_host(host=host)

    response_status, response_data = api_delete_host(host.id)

    assert_response_status(response_status, expected_status=200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)


def test_delete_hosts_using_filter(
    event_producer_mock, db_create_multiple_hosts, db_get_hosts, api_delete_filtered_hosts, patch_xjoin_post
):

    created_hosts = db_create_multiple_hosts(how_many=len(XJOIN_HOSTS_RESPONSE_FOR_FILTERING["hosts"]["data"]))
    host_ids = [str(host.id) for host in created_hosts]

    # set the new host ids in the xjoin search reference.
    resp = deepcopy(XJOIN_HOSTS_RESPONSE_FOR_FILTERING)
    ind = 0
    for id in host_ids:
        resp["hosts"]["data"][ind]["id"] = id
        ind += 1
    response = {"data": resp}

    # Make the new hosts available in xjoin-search to make them available
    # for querying for deletion using filters
    patch_xjoin_post(response, status=200)

    new_hosts = db_create_multiple_hosts()
    new_ids = [str(host.id) for host in new_hosts]

    # delete hosts using the IDs supposedly returned by the query_filter
    response_status, response_data = api_delete_filtered_hosts({"insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5"})

    assert '"type": "delete"' in event_producer_mock.event
    assert_response_status(response_status, expected_status=202)
    assert len(host_ids) == response_data["hosts_deleted"]

    # check db for the deleted hosts using their IDs
    host_id_list = [str(host.id) for host in created_hosts]
    deleted_hosts = db_get_hosts(host_id_list)
    assert deleted_hosts.count() == 0

    # now verify that the second set of hosts still available.
    remaining_hosts = db_get_hosts(new_ids)
    assert len(new_hosts) == remaining_hosts.count()


def test_delete_all_hosts(
    event_producer_mock, db_create_multiple_hosts, db_get_hosts, api_delete_filtered_hosts, patch_xjoin_post
):
    created_hosts = db_create_multiple_hosts(how_many=len(XJOIN_HOSTS_RESPONSE_FOR_FILTERING["hosts"]["data"]))
    host_ids = [str(host.id) for host in created_hosts]

    # set the new host ids in the xjoin search reference.
    resp = deepcopy(XJOIN_HOSTS_RESPONSE_FOR_FILTERING)
    for ind, id in enumerate(host_ids)
        resp["hosts"]["data"][ind]["id"] = id
    response = {"data": resp}

    # Make the new hosts available in xjoin-search to make them available
    # for querying for deletion using filters
    patch_xjoin_post(response, status=200)

    new_hosts = db_create_multiple_hosts()
    new_ids = [str(host.id) for host in new_hosts]

    # delete hosts using the IDs supposedly returned by the query_filter
    response_status, response_data = api_delete_filtered_hosts({"delete_all": True, "confirm": True})

    assert '"type": "delete"' in event_producer_mock.event
    assert_response_status(response_status, expected_status=202)
    assert len(host_ids) == response_data["hosts_deleted"]

    # check db for the deleted hosts using their IDs
    host_id_list = [str(host.id) for host in created_hosts]
    deleted_hosts = db_get_hosts(host_id_list)
    assert deleted_hosts.count() == 0

    # now verify that the second set of hosts still available.
    remaining_hosts = db_get_hosts(new_ids)
    assert len(new_hosts) == remaining_hosts.count()


def test_delete_all_hosts_no_delete_all_provided(
    db_create_multiple_hosts, api_delete_filtered_hosts, patch_xjoin_post
):
    created_hosts = db_create_multiple_hosts(how_many=len(XJOIN_HOSTS_RESPONSE_FOR_FILTERING["hosts"]["data"]))
    host_ids = [str(host.id) for host in created_hosts]

    # set the new host ids in the xjoin search reference.
    resp = deepcopy(XJOIN_HOSTS_RESPONSE_FOR_FILTERING)
    ind = 0
    for id in host_ids:
        resp["hosts"]["data"][ind]["id"] = id
        ind += 1
    response = {"data": resp}

    # Make the new hosts available in xjoin-search to make them available
    # for querying for deletion using filters
    patch_xjoin_post(response, status=200)

    # delete all hosts using incomplete filter
    response_status, response_data = api_delete_filtered_hosts({"confirm": True})

    assert_response_status(response_status, expected_status=400)
    assert "Deleting every host requires delete_all=true&confirm=true" in response_data["detail"]


def test_create_then_delete_check_metadata(event_datetime_mock, event_producer_mock, db_create_host, api_delete_host):
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


def test_delete_when_one_host_is_deleted(event_producer_mock, db_create_host, api_delete_host, mocker):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

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


def test_delete_host_with_RBAC_allowed(
    subtests,
    mocker,
    api_delete_host,
    event_datetime_mock,
    event_producer_mock,
    db_get_host,
    db_create_host,
    enable_rbac,
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            response_status, response_data = api_delete_host(host.id)

            assert_response_status(response_status, 200)

            assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

            assert not db_get_host(host.id)


def test_delete_host_with_RBAC_denied(
    subtests, mocker, api_delete_host, event_producer_mock, db_create_host, db_get_host, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            response_status, response_data = api_delete_host(host.id)

            assert_response_status(response_status, 403)

            assert db_get_host(host.id)


def test_delete_host_with_RBAC_bypassed_as_system(
    api_delete_host, event_datetime_mock, event_producer_mock, db_get_host, db_create_host, enable_rbac
):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    response_status, response_data = api_delete_host(host.id, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=host, timestamp=event_datetime_mock)

    assert not db_get_host(host.id)


def test_delete_hosts_chunk_size(
    event_producer_mock, db_create_multiple_hosts, api_delete_host, mocker, inventory_config
):
    inventory_config.host_delete_chunk_size = 5

    query_wraper = DeleteQueryWrapper(mocker)
    mocker.patch("api.host._get_host_list_by_id_list", query_wraper.mock_get_host_list_by_id_list)

    hosts = db_create_multiple_hosts(how_many=2)
    host_id_list = [str(host.id) for host in hosts]

    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=200)

    query_wraper.query.limit.assert_called_with(5)


@pytest.mark.parametrize(
    "send_side_effects",
    ((mock.Mock(), mock.Mock(**{"get.side_effect": KafkaError()})), (mock.Mock(), KafkaError("oops"))),
)
def test_delete_stops_after_kafka_producer_error(
    send_side_effects, kafka_producer, event_producer, db_create_multiple_hosts, api_delete_host, db_get_hosts
):
    event_producer._kafka_producer.send.side_effect = send_side_effects

    hosts = db_create_multiple_hosts(how_many=3)
    host_id_list = [str(host.id) for host in hosts]

    response_status, response_data = api_delete_host(",".join(host_id_list))

    assert_response_status(response_status, expected_status=500)

    remaining_hosts = db_get_hosts(host_id_list)
    assert remaining_hosts.count() == 1
    assert event_producer._kafka_producer.send.call_count == 2


class DeleteHostsMock:
    @classmethod
    def create_mock(cls, hosts_ids_to_delete):
        def _constructor(select_query, event_producer, chunk_size):
            return cls(hosts_ids_to_delete, select_query, event_producer, chunk_size)

        return _constructor

    def __init__(self, host_ids_to_delete, original_query, event_producer, chunk_size):
        self.host_ids_to_delete = host_ids_to_delete
        self.original_query = delete_hosts(original_query, event_producer, chunk_size)

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

    def mock_get_host_list_by_id_list(self, host_id_list):
        self.query = _get_host_list_by_id_list(host_id_list)
        self.query.limit = self.mocker.Mock(wraps=self.query.limit)
        return self.query
