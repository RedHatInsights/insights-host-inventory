#!/usr/bin/env python
import json
from datetime import datetime
from unittest import main
from unittest.mock import patch

from app.models import Host
from lib.host_delete import delete_hosts
from tests.test_api_utils import DbApiTestCase
from tests.test_api_utils import generate_uuid
from tests.test_api_utils import HOST_URL
from tests.test_api_utils import PreCreatedHostsBaseTestCase
from tests.test_delete_utils import DeleteHostsBaseTestCase


class DeleteHostsErrorTestCase(DbApiTestCase):
    def test_delete_non_existent_host(self):
        url = HOST_URL + "/" + generate_uuid()

        self.delete(url, 404)

    def test_delete_with_invalid_host_id(self):
        url = HOST_URL + "/" + "notauuid"

        self.delete(url, 400)


class DeleteHostsEventTestCase(PreCreatedHostsBaseTestCase, DeleteHostsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.host_to_delete = self.added_hosts[0]
        self.delete_url = HOST_URL + "/" + self.host_to_delete.id
        self.timestamp = datetime.utcnow()

    def _delete(self, url_query="", header=None):
        with patch("app.queue.events.datetime", **{"now.return_value": self.timestamp}):
            url = f"{self.delete_url}{url_query}"
            self.delete(url, 200, header, return_response_as_json=False)

    def _expected_metadata(self, expected_request_id):
        return {"request_id": expected_request_id}

    def test_create_then_delete(self):
        with self.app.app_context():
            self._check_hosts_are_present((self.host_to_delete.id,))
            self._delete()

            self._assert_event_is_valid(self.app.event_producer, self.host_to_delete, self.timestamp)
            self._check_hosts_are_deleted((self.host_to_delete.id,))

    def test_create_then_delete_with_branch_id(self):
        with self.app.app_context():
            self._check_hosts_are_present((self.host_to_delete.id,))
            self._delete(url_query="?branch_id=1234")

            self._assert_event_is_valid(self.app.event_producer, self.host_to_delete, self.timestamp)
            self._check_hosts_are_deleted((self.host_to_delete.id,))

    def test_create_then_delete_with_request_id(self):
        with self.app.app_context():
            request_id = generate_uuid()
            header = {"x-rh-insights-request-id": request_id}
            self._delete(header=header)

            self._assert_event_is_valid(self.app.event_producer, self.host_to_delete, self.timestamp)

            event = json.loads(self.app.event_producer.event)
            self.assertEqual(request_id, event["request_id"])

    def test_create_then_delete_without_request_id(self):
        with self.app.app_context():
            self._check_hosts_are_present((self.host_to_delete.id,))
            self._delete(header=None)

            self._assert_event_is_valid(self.app.event_producer, self.host_to_delete, self.timestamp)

            event = json.loads(self.app.event_producer.event)
            self.assertEqual("-1", event["request_id"])

    def test_create_then_delete_check_metadata(self):
        with self.app.app_context():
            self._check_hosts_are_present((self.host_to_delete.id,))

            request_id = generate_uuid()
            header = {"x-rh-insights-request-id": request_id}
            self._delete(header=header)

            self._assert_event_is_valid(self.app.event_producer, self.host_to_delete, self.timestamp)

            event = json.loads(self.app.event_producer.event)
            self.assertEqual(self._expected_metadata(request_id), event["metadata"])


class DeleteHostsRaceConditionTestCase(PreCreatedHostsBaseTestCase):
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

    def test_delete_when_one_host_is_deleted(self):
        host_id = self.added_hosts[0].id
        url = HOST_URL + "/" + host_id
        with patch("api.host.delete_hosts", self.DeleteHostsMock.create_mock([host_id])):
            # One host queried, but deleted by a different process. No event emitted yet returning
            # 200 OK.
            with self.app.app_context():
                self.delete(url, 200, return_response_as_json=False)
                self.assertIsNone(self.app.event_producer.event)

    def test_delete_when_all_hosts_are_deleted(self):
        host_id_list = [self.added_hosts[0].id, self.added_hosts[1].id]
        url = HOST_URL + "/" + ",".join(host_id_list)
        with patch("api.host.delete_hosts", self.DeleteHostsMock.create_mock(host_id_list)):
            with self.app.app_context():
                # Two hosts queried, but both deleted by a different process. No event emitted yet
                # returning 200 OK.
                self.delete(url, 200, return_response_as_json=False)
                self.assertIsNone(self.app.event_producer.event)

    def test_delete_when_some_hosts_is_deleted(self):
        host_id_list = [self.added_hosts[0].id, self.added_hosts[1].id]
        url = HOST_URL + "/" + ",".join(host_id_list)
        with patch("api.host.delete_hosts", self.DeleteHostsMock.create_mock(host_id_list[0:1])):
            with self.app.app_context():
                # Two hosts queried, one of them deleted by a different process. Only one event emitted,
                # returning 200 OK.
                self.delete(url, 200, return_response_as_json=False)
                self.assertEqual(host_id_list[1], self.app.event_producer.key)


if __name__ == "__main__":
    main()
