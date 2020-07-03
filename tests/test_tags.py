#!/usr/bin/env python
from unittest import main

from sqlalchemy import null

from app import db
from app.models import Host
from tests.test_api_utils import generate_uuid
from tests.test_api_utils import HOST_URL
from tests.test_api_utils import inject_qs
from tests.test_api_utils import PaginationBaseTestCase
from tests.test_api_utils import PreCreatedHostsBaseTestCase


class TagsPreCreatedHostsBaseTestCase(PreCreatedHostsBaseTestCase):
    def setUp(self):
        self.hosts_to_create = [("host4", generate_uuid(), "host4", [])]
        super().setUp()

    def _assert_host_ids_in_response(self, response, expected_hosts):
        response_ids = [host["id"] for host in response["results"]]
        expected_ids = [host.id for host in expected_hosts]
        self.assertEqual(response_ids, expected_ids)


class TagsTestCase(TagsPreCreatedHostsBaseTestCase, PaginationBaseTestCase):
    """
    Tests the tag endpoints
    """

    def test_get_tags_of_multiple_hosts(self):
        """
        Send a request for the tag count of 1 host and check
        that it is the correct number
        """
        expected_response = {host.id: host.tags for host in self.added_hosts}

        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)

        test_url = f"{HOST_URL}/{url_host_id_list}/tags?order_by=updated&order_how=ASC"
        response = self.get(test_url, 200)

        self.assertCountEqual(expected_response, response["results"])

        self._base_paging_test(test_url, len(expected_response))
        self._invalid_paging_parameters_test(test_url)

    def test_get_tag_count_of_multiple_hosts(self):
        expected_response = {
            added_host.id: len(host_to_create[3])
            for host_to_create, added_host in zip(self.hosts_to_create, self.added_hosts)
        }

        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)

        test_url = f"{HOST_URL}/{url_host_id_list}/tags/count?order_by=updated&order_how=ASC"
        response = self.get(test_url, 200)

        self.assertCountEqual(expected_response, response["results"])

        self._base_paging_test(test_url, len(expected_response))
        self._invalid_paging_parameters_test(test_url)

    def test_get_tags_of_hosts_that_doesnt_exist(self):
        """
        send a request for some hosts that don't exist
        """
        url_host_id = "fa28ec9b-5555-4b96-9b72-96129e0c3336"
        test_url = f"{HOST_URL}/{url_host_id}/tags"
        host_tag_results = self.get(test_url, 200)

        expected_response = {}

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_filtered_by_search_tags_of_multiple_hosts(self):
        """
        send a request for tags to one host with some searchTerm
        """
        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)
        for search, results in (
            (
                "",
                {
                    self.added_hosts[0].id: [
                        {"namespace": "NS1", "key": "key1", "value": "val1"},
                        {"namespace": "NS1", "key": "key2", "value": "val1"},
                        {"namespace": "SPECIAL", "key": "tag", "value": "ToFind"},
                        {"namespace": "no", "key": "key", "value": None},
                    ],
                    self.added_hosts[1].id: [
                        {"namespace": "NS1", "key": "key1", "value": "val1"},
                        {"namespace": "NS2", "key": "key2", "value": "val2"},
                        {"namespace": "NS3", "key": "key3", "value": "val3"},
                    ],
                    self.added_hosts[2].id: [
                        {"namespace": "NS2", "key": "key2", "value": "val2"},
                        {"namespace": "NS3", "key": "key3", "value": "val3"},
                        {"namespace": "NS1", "key": "key3", "value": "val3"},
                        {"namespace": None, "key": "key4", "value": "val4"},
                        {"namespace": None, "key": "key5", "value": None},
                    ],
                    self.added_hosts[3].id: [],
                },
            ),
            (
                "To",
                {
                    self.added_hosts[0].id: [{"namespace": "SPECIAL", "key": "tag", "value": "ToFind"}],
                    self.added_hosts[1].id: [],
                    self.added_hosts[2].id: [],
                    self.added_hosts[3].id: [],
                },
            ),
            (
                "NS1",
                {
                    self.added_hosts[0].id: [
                        {"namespace": "NS1", "key": "key1", "value": "val1"},
                        {"namespace": "NS1", "key": "key2", "value": "val1"},
                    ],
                    self.added_hosts[1].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                    self.added_hosts[2].id: [{"namespace": "NS1", "key": "key3", "value": "val3"}],
                    self.added_hosts[3].id: [],
                },
            ),
            (
                "key1",
                {
                    self.added_hosts[0].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                    self.added_hosts[1].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                    self.added_hosts[2].id: [],
                    self.added_hosts[3].id: [],
                },
            ),
            (
                "val1",
                {
                    self.added_hosts[0].id: [
                        {"namespace": "NS1", "key": "key1", "value": "val1"},
                        {"namespace": "NS1", "key": "key2", "value": "val1"},
                    ],
                    self.added_hosts[1].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                    self.added_hosts[2].id: [],
                    self.added_hosts[3].id: [],
                },
            ),
            (
                "e",
                {
                    self.added_hosts[0].id: [
                        {"namespace": "NS1", "key": "key1", "value": "val1"},
                        {"namespace": "NS1", "key": "key2", "value": "val1"},
                        {"namespace": "no", "key": "key", "value": None},
                    ],
                    self.added_hosts[1].id: [
                        {"namespace": "NS1", "key": "key1", "value": "val1"},
                        {"namespace": "NS2", "key": "key2", "value": "val2"},
                        {"namespace": "NS3", "key": "key3", "value": "val3"},
                    ],
                    self.added_hosts[2].id: [
                        {"namespace": "NS2", "key": "key2", "value": "val2"},
                        {"namespace": "NS3", "key": "key3", "value": "val3"},
                        {"namespace": "NS1", "key": "key3", "value": "val3"},
                        {"namespace": None, "key": "key4", "value": "val4"},
                        {"namespace": None, "key": "key5", "value": None},
                    ],
                    self.added_hosts[3].id: [],
                },
            ),
            (
                " ",
                {
                    self.added_hosts[0].id: [],
                    self.added_hosts[1].id: [],
                    self.added_hosts[2].id: [],
                    self.added_hosts[3].id: [],
                },
            ),
        ):
            with self.subTest(search=search):
                test_url = f"{HOST_URL}/{url_host_id_list}/tags?search={search}"
                response = self.get(test_url, 200)
                self.assertCountEqual(results.keys(), response["results"].keys())
                for host_id, tags in results.items():
                    self.assertCountEqual(tags, response["results"][host_id])

    def test_get_tags_count_of_hosts_that_doesnt_exist(self):
        """
        send a request for some hosts that don't exist
        """
        url_host_id = "fa28ec9b-5555-4b96-9b72-96129e0c3336"
        test_url = f"{HOST_URL}/{url_host_id}/tags/count"
        host_tag_results = self.get(test_url, 200)

        expected_response = {}

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_tags_from_host_with_no_tags(self):
        """
        send a request for a host with no tags
        """
        host_with_no_tags = self.added_hosts[3]
        expected_response = {host_with_no_tags.id: []}

        test_url = f"{HOST_URL}/{host_with_no_tags.id}/tags"
        host_tag_results = self.get(test_url, 200)

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_tags_from_host_with_null_tags(self):
        # FIXME: Remove this test after migration to NOT NULL.
        for empty in (None, null()):
            with self.subTest(tags=empty):
                host_id = self.added_hosts[0].id

                with self.app.app_context():
                    host = Host.query.get(host_id)
                    host.tags = empty
                    db.session.add(host)
                    db.session.commit()

                host_tag_results = self.get(f"{HOST_URL}/{host_id}/tags", 200)

                self.assertEqual({host_id: []}, host_tag_results["results"])

    def test_get_tags_count_from_host_with_null_tags(self):
        # FIXME: Remove this test after migration to NOT NULL.
        for empty in (None, null()):
            with self.subTest(tags=empty):
                host_id = self.added_hosts[0].id

                with self.app.app_context():
                    host = Host.query.get(host_id)
                    host.tags = empty
                    db.session.add(host)
                    db.session.commit()

                host_tag_results = self.get(f"{HOST_URL}/{host_id}/tags/count", 200)

                self.assertEqual({host_id: 0}, host_tag_results["results"])

    def test_get_tags_count_from_host_with_no_tags(self):
        """
        send a request for a host with no tags
        """
        host_with_no_tags = self.added_hosts[3]
        expected_response = {host_with_no_tags.id: 0}

        test_url = f"{HOST_URL}/{host_with_no_tags.id}/tags/count"
        host_tag_results = self.get(test_url, 200)

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_tags_count_from_host_with_tag_with_no_value(self):
        # host 0 has 4 tags, one of which has no value
        host_with_valueless_tag = self.added_hosts[0]
        expected_response = {host_with_valueless_tag.id: 4}

        test_url = f"{HOST_URL}/{host_with_valueless_tag.id}/tags/count"
        host_tag_results = self.get(test_url, 200)

        self.assertEqual(expected_response, host_tag_results["results"])

    def _per_page_test(self, url, per_page, num_pages):
        for i in range(0, num_pages):
            page = i + 1
            with self.subTest(page=page):
                url = inject_qs(url, page=str(page), per_page=str(per_page))
                response = self.get(url, 200)
                yield response

    def _assert_paginated_response_counts(self, response, per_page, total):
        self.assertEqual(len(response["results"]), per_page)
        self.assertEqual(response["count"], per_page)
        self.assertEqual(response["total"], total)

    def _assert_response_tags(self, response, host_tags):
        self.assertCountEqual(response["results"].keys(), host_tags.keys())
        for host_id, tags in host_tags.items():
            self.assertCountEqual(response["results"][host_id], tags)

    def _assert_response_tag_counts(self, response, host_tag_counts):
        self.assertCountEqual(response["results"].keys(), host_tag_counts.keys())
        for host_id, tag_count in host_tag_counts.items():
            self.assertEqual(response["results"][host_id], tag_count)

    def test_tags_pagination(self):
        """
        simple test to check pagination works for /tags
        """
        host_list = self.added_hosts
        url_host_id_list = self._build_host_id_list_for_url(host_list)

        expected_responses_1_per_page = [
            {added_host.id: host_to_create[3]}
            for host_to_create, added_host in zip(self.hosts_to_create, self.added_hosts)
        ]

        test_url = f"{HOST_URL}/{url_host_id_list}/tags?order_by=updated&order_how=ASC"

        # 1 per page test
        for response in self._per_page_test(test_url, 1, len(host_list)):
            self._assert_paginated_response_counts(response, 1, len(self.added_hosts))
            self._assert_response_tags(response, expected_responses_1_per_page[response["page"] - 1])

        expected_responses_2_per_page = [
            {self.added_hosts[0].id: self.hosts_to_create[0][3], self.added_hosts[1].id: self.hosts_to_create[1][3]},
            {self.added_hosts[2].id: self.hosts_to_create[2][3], self.added_hosts[3].id: self.hosts_to_create[3][3]},
        ]

        # 2 per page test
        for response in self._per_page_test(test_url, 2, 2):
            self._assert_paginated_response_counts(response, 2, len(self.added_hosts))
            self._assert_response_tags(response, expected_responses_2_per_page[response["page"] - 1])

    def test_tags_count_pagination(self):
        """
        simple test to check pagination works for /tags
        """
        host_list = self.added_hosts
        url_host_id_list = self._build_host_id_list_for_url(host_list)

        expected_responses_1_per_page = [
            {added_host.id: len(host_to_create[3])}
            for host_to_create, added_host in zip(self.hosts_to_create, self.added_hosts)
        ]

        test_url = f"{HOST_URL}/{url_host_id_list}/tags/count?order_by=updated&order_how=ASC"

        # 1 per page test
        for response in self._per_page_test(test_url, 1, len(host_list)):
            self._assert_paginated_response_counts(response, 1, len(self.added_hosts))
            self._assert_response_tag_counts(response, expected_responses_1_per_page[response["page"] - 1])

        expected_responses_2_per_page = [
            {
                self.added_hosts[0].id: len(self.hosts_to_create[0][3]),
                self.added_hosts[1].id: len(self.hosts_to_create[1][3]),
            },
            {
                self.added_hosts[2].id: len(self.hosts_to_create[2][3]),
                self.added_hosts[3].id: len(self.hosts_to_create[3][3]),
            },
        ]

        # 2 per page test
        for response in self._per_page_test(test_url, 2, 2):
            self._assert_paginated_response_counts(response, 2, len(self.added_hosts))
            self._assert_response_tag_counts(response, expected_responses_2_per_page[response["page"] - 1])


if __name__ == "__main__":
    main()
