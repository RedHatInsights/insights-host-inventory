from datetime import timezone
from json import loads

from app.models import Host
from tests.test_api_utils import DbApiTestCase
from tests.test_api_utils import HOST_URL


class DeleteHostsBaseTestCase(DbApiTestCase):
    def _get_hosts(self, host_ids):
        url_part = ",".join(host_ids)
        return self.get(f"{HOST_URL}/{url_part}", 200)

    def _assert_event_is_valid(self, event_producer, host, timestamp):
        event = loads(event_producer.event)

        self.assertIsInstance(event, dict)
        expected_keys = {"timestamp", "type", "id", "account", "insights_id", "request_id", "metadata"}
        self.assertEqual(set(event.keys()), expected_keys)

        self.assertEqual(timestamp.replace(tzinfo=timezone.utc).isoformat(), event["timestamp"])
        self.assertEqual("delete", event["type"])

        self.assertEqual(host.insights_id, event["insights_id"])

        self.assertEqual(event_producer.key, host.id)
        self.assertEqual(event_producer.headers, {"event_type": "delete"})

    def _get_hosts_from_db(self, host_ids):
        with self.app.app_context():
            return tuple(str(host.id) for host in Host.query.filter(Host.id.in_(host_ids)))

    def _check_hosts_are_present(self, host_ids):
        retrieved_ids = self._get_hosts_from_db(host_ids)
        self.assertEqual(retrieved_ids, host_ids)

    def _check_hosts_are_deleted(self, host_ids):
        retrieved_ids = self._get_hosts_from_db(host_ids)
        self.assertEqual(retrieved_ids, ())
