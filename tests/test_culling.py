#!/usr/bin/env python
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest import main
from unittest import mock
from unittest.mock import patch

import pytest

from app import db
from app.utils import HostWrapper
from host_reaper import run as host_reaper_run
from tests.test_api_delete import DeleteHostsBaseTestCase
from tests.test_api_utils import ACCOUNT
from tests.test_api_utils import DbApiTestCase
from tests.test_api_utils import generate_uuid
from tests.test_api_utils import HOST_URL
from tests.test_api_utils import now
from tests.test_api_utils import test_data
from tests.test_culling_utils import HostStalenessBaseTestCase
from tests.test_utils import MockEventProducer


class QueryStaleTimestampTestCase(DbApiTestCase):
    def test_with_stale_timestamp(self):
        def _assert_values(response_host):
            self.assertIn("stale_timestamp", response_host)
            self.assertIn("stale_warning_timestamp", response_host)
            self.assertIn("culled_timestamp", response_host)
            self.assertIn("reporter", response_host)
            self.assertEqual(stale_timestamp_str, response_host["stale_timestamp"])
            self.assertEqual(stale_warning_timestamp_str, response_host["stale_warning_timestamp"])
            self.assertEqual(culled_timestamp_str, response_host["culled_timestamp"])
            self.assertEqual(reporter, response_host["reporter"])

        stale_timestamp = now()
        stale_timestamp_str = stale_timestamp.isoformat()
        stale_warning_timestamp = stale_timestamp + timedelta(weeks=1)
        stale_warning_timestamp_str = stale_warning_timestamp.isoformat()
        culled_timestamp = stale_timestamp + timedelta(weeks=2)
        culled_timestamp_str = culled_timestamp.isoformat()
        reporter = "some reporter"

        host_to_create = HostWrapper(
            {"account": ACCOUNT, "fqdn": "matching fqdn", "stale_timestamp": stale_timestamp_str, "reporter": reporter}
        )

        create_response = self.post(HOST_URL, [host_to_create.data()], 207)
        self._verify_host_status(create_response, 0, 201)
        created_host = self._pluck_host_from_response(create_response, 0)
        _assert_values(created_host)

        update_response = self.post(HOST_URL, [host_to_create.data()], 207)
        self._verify_host_status(update_response, 0, 200)
        updated_host = self._pluck_host_from_response(update_response, 0)
        _assert_values(updated_host)

        get_list_response = self.get(HOST_URL, 200)
        _assert_values(get_list_response["results"][0])

        created_host_id = created_host["id"]
        get_by_id_response = self.get(f"{HOST_URL}/{created_host_id}", 200)
        _assert_values(get_by_id_response["results"][0])


class QueryHostsStalenessBaseTestCase(HostStalenessBaseTestCase):
    def _get_hosts_by_id_url(self, host_id_list, endpoint="", query=""):
        host_id_query = ",".join(host_id_list)
        return f"{HOST_URL}/{host_id_query}{endpoint}{query}"

    def _get_hosts_by_id(self, host_id_list, endpoint="", query=""):
        url = self._get_hosts_by_id_url(host_id_list, endpoint, query)
        response = self.get(url, 200)
        return response["results"]


class QueryStalenessGetHostsBaseTestCase(QueryHostsStalenessBaseTestCase, HostStalenessBaseTestCase):
    def _created_hosts(self):
        return (self.fresh_host["id"], self.stale_host["id"], self.stale_warning_host["id"], self.culled_host["id"])

    def _get_all_hosts_url(self, query):
        return f"{HOST_URL}{query}"

    def _get_all_hosts(self, query):
        url = self._get_all_hosts_url(query)
        response = self.get(url, 200)
        return tuple(host["id"] for host in response["results"])

    def _get_created_hosts_by_id_url(self, query):
        return self._get_hosts_by_id_url(self._created_hosts(), query=query)


class QueryStalenessGetHostsTestCase(QueryStalenessGetHostsBaseTestCase):
    def _get_endpoint_query_results(self, endpoint="", query=""):
        hosts = self._get_hosts_by_id(self._created_hosts(), endpoint, query)
        if endpoint == "/tags" or endpoint == "/tags/count":
            return tuple(hosts.keys())
        else:
            return tuple(host["id"] for host in hosts)

    def test_dont_get_only_culled(self):
        self.get(self._get_all_hosts_url(query="?staleness=culled"), 400)

    def test_get_only_fresh(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=fresh")
        self.assertEqual((self.fresh_host["id"],), retrieved_host_ids)

    def test_get_only_stale(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=stale")
        self.assertEqual((self.stale_host["id"],), retrieved_host_ids)

    def test_get_only_stale_warning(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=stale_warning")
        self.assertEqual((self.stale_warning_host["id"],), retrieved_host_ids)

    def test_get_only_unknown(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=unknown")
        self.assertEqual((self.unknown_host["id"],), retrieved_host_ids)

    def test_get_multiple_states(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=fresh,stale")
        self.assertEqual((self.stale_host["id"], self.fresh_host["id"]), retrieved_host_ids)

    def test_get_hosts_list_default_ignores_culled(self):
        retrieved_host_ids = self._get_all_hosts("")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_get_hosts_by_id_default_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_tags_default_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("/tags")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_tags_count_default_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("/tags/count")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_get_system_profile_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("/system_profile")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)


class QueryStalenessPatchIgnoresCulledTestCase(QueryStalenessGetHostsBaseTestCase):
    def test_patch_ignores_culled(self):
        url = HOST_URL + "/" + self.culled_host["id"]
        self.patch(url, {"display_name": "patched"}, 404)

    def test_patch_works_on_non_culled(self):
        with self.app.app_context():
            url = HOST_URL + "/" + self.fresh_host["id"]
            self.patch(url, {"display_name": "patched"}, 200)

    def test_patch_facts_ignores_culled(self):
        url = HOST_URL + "/" + self.culled_host["id"] + "/facts/ns1"
        self.patch(url, {"ARCHITECTURE": "patched"}, 400)

    def test_patch_facts_works_on_non_culled(self):
        url = HOST_URL + "/" + self.fresh_host["id"] + "/facts/ns1"
        self.patch(url, {"ARCHITECTURE": "patched"}, 200)

    def test_put_facts_ignores_culled(self):
        url = HOST_URL + "/" + self.culled_host["id"] + "/facts/ns1"
        self.put(url, {"ARCHITECTURE": "patched"}, 400)

    def test_put_facts_works_on_non_culled(self):
        url = HOST_URL + "/" + self.fresh_host["id"] + "/facts/ns1"
        self.put(url, {"ARCHITECTURE": "patched"}, 200)


class QueryStalenessDeleteIgnoresCulledTestCase(QueryStalenessGetHostsBaseTestCase):
    def test_delete_ignores_culled(self):
        url = HOST_URL + "/" + self.culled_host["id"]
        self.delete(url, 404)

    def test_delete_works_on_non_culled(self):
        with self.app.app_context():
            url = HOST_URL + "/" + self.fresh_host["id"]
            self.delete(url, 200, return_response_as_json=False)


class QueryStalenessGetHostsIgnoresStalenessParameterTestCase(QueryStalenessGetHostsTestCase):
    def _check_query_fails(self, endpoint="", query=""):
        url = self._get_hosts_by_id_url(self._created_hosts(), endpoint, query)
        self.get(url, 400)

    def test_get_host_by_id_doesnt_use_staleness_parameter(self):
        self._check_query_fails(query="?staleness=fresh")

    def test_tags_doesnt_use_staleness_parameter(self):
        self._check_query_fails("/tags", "?staleness=fresh")

    def test_tags_count_doesnt_use_staleness_parameter(self):
        self._check_query_fails("/tags/count", "?staleness=fresh")

    def test_sytem_profile_doesnt_use_staleness_parameter(self):
        self._check_query_fails("/system_profile", "?staleness=fresh")


class QueryStalenessConfigTimestampsTestCase(QueryHostsStalenessBaseTestCase):
    def _create_and_get_host(self, stale_timestamp):
        host_to_create = self._create_host(stale_timestamp)
        retrieved_host = self._get_hosts_by_id((host_to_create["id"],))[0]
        self.assertEqual(stale_timestamp.isoformat(), retrieved_host["stale_timestamp"])
        return retrieved_host

    def test_stale_warning_timestamp(self):
        for culling_stale_warning_offset_days in (1, 7, 12):
            with self.subTest(culling_stale_warning_offset_days=culling_stale_warning_offset_days):
                config = self.app.config["INVENTORY_CONFIG"]
                config.culling_stale_warning_offset_days = culling_stale_warning_offset_days

                stale_timestamp = datetime.now(timezone.utc) + timedelta(hours=1)
                host = self._create_and_get_host(stale_timestamp)

                stale_warning_timestamp = stale_timestamp + timedelta(days=culling_stale_warning_offset_days)
                self.assertEqual(stale_warning_timestamp.isoformat(), host["stale_warning_timestamp"])

    def test_culled_timestamp(self):
        for culling_culled_offset_days in (8, 14, 20):
            with self.subTest(culling_culled_offset_days=culling_culled_offset_days):
                config = self.app.config["INVENTORY_CONFIG"]
                config.culling_culled_offset_days = culling_culled_offset_days

                stale_timestamp = datetime.now(timezone.utc) + timedelta(hours=1)
                host = self._create_and_get_host(stale_timestamp)

                culled_timestamp = stale_timestamp + timedelta(days=culling_culled_offset_days)
                self.assertEqual(culled_timestamp.isoformat(), host["culled_timestamp"])


class HostReaperTestCase(DeleteHostsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.now_timestamp = datetime.now(timezone.utc)
        self.staleness_timestamps = {
            "fresh": self.now_timestamp + timedelta(hours=1),
            "stale": self.now_timestamp,
            "stale_warning": self.now_timestamp - timedelta(weeks=1),
            "culled": self.now_timestamp - timedelta(weeks=2),
        }
        self.event_producer = MockEventProducer()

    def _run_host_reaper(self):
        with patch("app.queue.events.datetime", **{"now.return_value": self.now_timestamp}):
            with self.app.app_context():
                config = self.app.config["INVENTORY_CONFIG"]
                host_reaper_run(config, mock.Mock(), db.session, self.event_producer)

    def _add_hosts(self, data):
        post = []
        for d in data:
            host = HostWrapper(test_data(insights_id=generate_uuid(), **d))
            post.append(host.data())

        response = self.post(HOST_URL, post, 207)

        hosts = []
        for i in range(len(data)):
            self._verify_host_status(response, i, 201)
            added_host = self._pluck_host_from_response(response, i)
            hosts.append(HostWrapper(added_host))

        return hosts

    def _get_hosts(self, host_ids):
        url_part = ",".join(host_ids)
        return self.get(f"{HOST_URL}/{url_part}")

    @pytest.mark.host_reaper
    def test_culled_host_is_removed(self):
        with self.app.app_context():
            added_host = self._add_hosts(
                ({"stale_timestamp": self.staleness_timestamps["culled"].isoformat(), "reporter": "some reporter"},)
            )[0]
            self._check_hosts_are_present((added_host.id,))

            self._run_host_reaper()
            self._check_hosts_are_deleted((added_host.id,))

            self._assert_event_is_valid(self.event_producer, added_host, self.now_timestamp)

    @pytest.mark.host_reaper
    def test_non_culled_host_is_not_removed(self):
        hosts_to_add = []
        for stale_timestamp in (
            self.staleness_timestamps["stale_warning"],
            self.staleness_timestamps["stale"],
            self.staleness_timestamps["fresh"],
        ):
            hosts_to_add.append({"stale_timestamp": stale_timestamp.isoformat(), "reporter": "some reporter"})

        added_hosts = self._add_hosts(hosts_to_add)
        added_host_ids = tuple(host.id for host in added_hosts)
        self._check_hosts_are_present(added_host_ids)

        self._run_host_reaper()
        self._check_hosts_are_present(added_host_ids)
        self.assertIsNone(self.event_producer.event)

    @pytest.mark.host_reaper
    def test_unknown_host_is_not_removed(self):
        with self.app.app_context():
            added_hosts = self._add_hosts(({},))
            added_host_id = added_hosts[0].id
            self._check_hosts_are_present((added_host_id,))

            self._run_host_reaper()
            self._check_hosts_are_present((added_host_id,))
            self.assertIsNone(self.event_producer.event)


if __name__ == "__main__":
    main()
