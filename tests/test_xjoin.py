#!/usr/bin/env python
import json
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from functools import partial
from unittest import main
from unittest import mock
from unittest.mock import ANY
from unittest.mock import patch

from api.host_query_xjoin import QUERY as HOST_QUERY
from api.tag import TAGS_QUERY
from tests.test_api_utils import ApiBaseTestCase
from tests.test_api_utils import DbApiBaseTestCase
from tests.test_api_utils import generate_uuid
from tests.test_api_utils import HOST_URL
from tests.test_api_utils import quote
from tests.test_api_utils import quote_everything
from tests.test_api_utils import TAGS_URL
from tests.test_utils import set_environment

MOCK_XJOIN_HOST_RESPONSE = {
    "hosts": {
        "meta": {"total": 2},
        "data": [
            {
                "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                "account": "test",
                "display_name": "test01.rhel7.jharting.local",
                "ansible_host": "test01.rhel7.jharting.local",
                "created_on": "2019-02-10T08:07:03.354307Z",
                "modified_on": "2019-02-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test01.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                },
                "facts": None,
                "stale_timestamp": "2020-02-10T08:07:03.354307Z",
                "reporter": "puptoo",
            },
            {
                "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                "account": "test",
                "display_name": "test02.rhel7.jharting.local",
                "ansible_host": "test02.rhel7.jharting.local",
                "created_on": "2019-01-10T08:07:03.354307Z",
                "modified_on": "2019-01-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test02.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                },
                "facts": {
                    "os": {"os.release": "Red Hat Enterprise Linux Server"},
                    "bios": {
                        "bios.vendor": "SeaBIOS",
                        "bios.release_date": "2014-04-01",
                        "bios.version": "1.11.0-2.el7",
                    },
                },
                "stale_timestamp": "2020-01-10T08:07:03.354307Z",
                "reporter": "puptoo",
            },
        ],
    }
}


class XjoinRequestBaseTestCase(ApiBaseTestCase):
    @contextmanager
    def _patch_xjoin_post(self, response, status=200):
        with patch(
            "app.xjoin.post",
            **{
                "return_value.text": json.dumps(response),
                "return_value.json.return_value": response,
                "return_value.status_code": status,
            },
        ) as post:
            yield post

    def _get_with_request_id(self, url, request_id, status=200):
        return self.get(url, status, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"})

    def _assert_called_with_headers(self, post, request_id):
        identity = self._get_valid_auth_header()["x-rh-identity"].decode()
        post.assert_called_once_with(
            ANY, json=ANY, headers={"x-rh-identity": identity, "x-rh-insights-request-id": request_id}
        )


class HostsXjoinBaseTestCase(ApiBaseTestCase):
    def setUp(self):
        with set_environment({"BULK_QUERY_SOURCE": "xjoin"}):
            super().setUp()


class HostsXjoinRequestBaseTestCase(XjoinRequestBaseTestCase, HostsXjoinBaseTestCase):
    EMPTY_RESPONSE = {"hosts": {"meta": {"total": 0}, "data": []}}
    patch_graphql_query_empty_response = partial(
        patch, "api.host_query_xjoin.graphql_query", return_value=EMPTY_RESPONSE
    )


class HostsXjoinRequestHeadersTestCase(HostsXjoinRequestBaseTestCase):
    def test_headers_forwarded(self):
        with self._patch_xjoin_post({"data": self.EMPTY_RESPONSE}) as post:
            request_id = generate_uuid()
            self._get_with_request_id(HOST_URL, request_id)
            self._assert_called_with_headers(post, request_id)


class XjoinSearchResponseCheckingTestCase(XjoinRequestBaseTestCase, HostsXjoinBaseTestCase):
    EMPTY_RESPONSE = {"hosts": {"meta": {"total": 0}, "data": []}}

    def base_xjoin_response_status_test(self, xjoin_res_status, expected_HBI_res_status):
        with self._patch_xjoin_post({"data": self.EMPTY_RESPONSE}, xjoin_res_status):
            request_id = generate_uuid()
            self._get_with_request_id(HOST_URL, request_id, expected_HBI_res_status)

    def test_host_request_xjoin_status_403(self):
        self.base_xjoin_response_status_test(403, 500)

    def test_host_request_xjoin_status_200(self):
        self.base_xjoin_response_status_test(200, 200)


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterSearchTestCase(HostsXjoinRequestBaseTestCase):
    STALENESS_ANY = ANY

    def test_query_variables_fqdn(self, graphql_query):
        fqdn = "host.domain.com"
        self.get(f"{HOST_URL}?fqdn={quote(fqdn)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": ({"fqdn": {"eq": fqdn}}, self.STALENESS_ANY),
            },
        )

    def test_query_variables_display_name(self, graphql_query):
        display_name = "my awesome host uwu"
        self.get(f"{HOST_URL}?display_name={quote(display_name)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": ({"display_name": {"matches": f"*{display_name}*"}}, self.STALENESS_ANY),
            },
        )

    def test_query_variables_hostname_or_id_non_uuid(self, graphql_query):
        hostname_or_id = "host.domain.com"
        self.get(f"{HOST_URL}?hostname_or_id={quote(hostname_or_id)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": (
                    {
                        "OR": (
                            {"display_name": {"matches": f"*{hostname_or_id}*"}},
                            {"fqdn": {"matches": f"*{hostname_or_id}*"}},
                        )
                    },
                    self.STALENESS_ANY,
                ),
            },
        )

    def test_query_variables_hostname_or_id_uuid(self, graphql_query):
        hostname_or_id = generate_uuid()
        self.get(f"{HOST_URL}?hostname_or_id={quote(hostname_or_id)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": (
                    {
                        "OR": (
                            {"display_name": {"matches": f"*{hostname_or_id}*"}},
                            {"fqdn": {"matches": f"*{hostname_or_id}*"}},
                            {"id": {"eq": hostname_or_id}},
                        )
                    },
                    self.STALENESS_ANY,
                ),
            },
        )

    def test_query_variables_insights_id(self, graphql_query):
        insights_id = generate_uuid()
        self.get(f"{HOST_URL}?insights_id={quote(insights_id)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": ({"insights_id": {"eq": insights_id}}, self.STALENESS_ANY),
            },
        )

    def test_query_variables_none(self, graphql_query):
        self.get(HOST_URL, 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {"order_by": ANY, "order_how": ANY, "limit": ANY, "offset": ANY, "filter": (self.STALENESS_ANY,)},
        )

    def test_query_variables_priority(self, graphql_query):
        param = quote(generate_uuid())
        for filter_, query in (
            ("fqdn", f"fqdn={param}&display_name={param}"),
            ("fqdn", f"fqdn={param}&hostname_or_id={param}"),
            ("fqdn", f"fqdn={param}&insights_id={param}"),
            ("display_name", f"display_name={param}&hostname_or_id={param}"),
            ("display_name", f"display_name={param}&insights_id={param}"),
            ("OR", f"hostname_or_id={param}&insights_id={param}"),
        ):
            with self.subTest(filter=filter_, query=query):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?{query}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": ({filter_: ANY}, self.STALENESS_ANY),
                    },
                )


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterTagsTestCase(HostsXjoinRequestBaseTestCase):
    STALENESS_ANY = ANY

    def test_query_variables_tags(self, graphql_query):
        for tags, query_param in (
            (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},), "a/b=c"),
            (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": None}},), "a/b"),
            (
                (
                    {"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},
                    {"namespace": {"eq": "d"}, "key": {"eq": "e"}, "value": {"eq": "f"}},
                ),
                "a/b=c,d/e=f",
            ),
            (
                ({"namespace": {"eq": "a/a=a"}, "key": {"eq": "b/b=b"}, "value": {"eq": "c/c=c"}},),
                quote("a/a=a") + "/" + quote("b/b=b") + "=" + quote("c/c=c"),
            ),
            (({"namespace": {"eq": "ɑ"}, "key": {"eq": "β"}, "value": {"eq": "ɣ"}},), "ɑ/β=ɣ"),
        ):
            with self.subTest(tags=tags, query_param=query_param):
                graphql_query.reset_mock()

                self.get(f"{HOST_URL}?tags={quote(query_param)}")

                tag_filters = tuple({"tag": item} for item in tags)

                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": tag_filters + (self.STALENESS_ANY,),
                    },
                )

    def test_query_variables_tags_with_search(self, graphql_query):
        for field in ("fqdn", "display_name", "hostname_or_id", "insights_id"):
            with self.subTest(field=field):
                graphql_query.reset_mock()

                value = quote(generate_uuid())
                self.get(f"{HOST_URL}?{field}={value}&tags=a/b=c")

                search_any = ANY
                tag_filter = {"tag": {"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}}}
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": (search_any, tag_filter, self.STALENESS_ANY),
                    },
                )


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterRegisteredWithTestCase(HostsXjoinRequestBaseTestCase):
    STALENESS_ANY = ANY

    def _get_host_registered_with(self, service):
        self.get(f"{HOST_URL}?registered_with={service}")

    def test_query_variables_registered_with_insights(self, graphql_query):
        graphql_query.reset_mock()

        self._get_host_registered_with("insights")

        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": (self.STALENESS_ANY, {"NOT": {"insights_id": {"eq": None}}}),
            },
        )


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestOrderingTestCase(HostsXjoinRequestBaseTestCase):
    def test_query_variables_ordering_dir(self, graphql_query):
        for direction in ("ASC", "DESC"):
            with self.subTest(direction=direction):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?order_by=updated&order_how={quote(direction)}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY, {"limit": ANY, "offset": ANY, "order_by": ANY, "order_how": direction, "filter": ANY}
                )

    def test_query_variables_ordering_by(self, graphql_query):
        for params_order_by, xjoin_order_by, default_xjoin_order_how in (
            ("updated", "modified_on", "DESC"),
            ("display_name", "display_name", "ASC"),
        ):
            with self.subTest(ordering=params_order_by):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?order_by={quote(params_order_by)}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "limit": ANY,
                        "offset": ANY,
                        "order_by": xjoin_order_by,
                        "order_how": default_xjoin_order_how,
                        "filter": ANY,
                    },
                )

    def test_query_variables_ordering_by_invalid(self, graphql_query):
        self.get(f"{HOST_URL}?order_by=fqdn", 400)
        graphql_query.assert_not_called()

    def test_query_variables_ordering_dir_invalid(self, graphql_query):
        self.get(f"{HOST_URL}?order_by=updated&order_how=REVERSE", 400)
        graphql_query.assert_not_called()

    def test_query_variables_ordering_dir_without_by(self, graphql_query):
        self.get(f"{HOST_URL}?order_how=ASC", 400)
        graphql_query.assert_not_called()


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestPaginationTestCase(HostsXjoinRequestBaseTestCase):
    def test_response_pagination(self, graphql_query):
        for page, limit, offset in ((1, 2, 0), (2, 2, 2), (4, 50, 150)):
            with self.subTest(page=page, limit=limit, offset=offset):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?per_page={quote(limit)}&page={quote(page)}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY, {"order_by": ANY, "order_how": ANY, "limit": limit, "offset": offset, "filter": ANY}
                )

    def test_response_invalid_pagination(self, graphql_query):
        for page, per_page in ((0, 10), (-1, 10), (1, 0), (1, -5), (1, 101)):
            with self.subTest(page=page):
                self.get(f"{HOST_URL}?per_page={quote(per_page)}&page={quote(page)}", 400)
                graphql_query.assert_not_called()


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterStalenessTestCase(HostsXjoinRequestBaseTestCase):
    def _assert_graph_query_single_call_with_staleness(self, graphql_query, staleness_conditions):
        conditions = tuple({"stale_timestamp": staleness_condition} for staleness_condition in staleness_conditions)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {"order_by": ANY, "order_how": ANY, "limit": ANY, "offset": ANY, "filter": ({"OR": conditions},)},
        )

    def test_query_variables_default_except_staleness(self, graphql_query):
        self.get(HOST_URL, 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY, {"order_by": "modified_on", "order_how": "DESC", "limit": 50, "offset": 0, "filter": ANY}
        )

    @patch(
        "app.culling.datetime", **{"now.return_value": datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)}
    )
    def test_query_variables_default_staleness(self, datetime_mock, graphql_query):
        self.get(HOST_URL, 200)
        self._assert_graph_query_single_call_with_staleness(
            graphql_query,
            (
                {"gt": "2019-12-16T10:10:06.754201+00:00"},  # fresh
                {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"},  # stale
            ),
        )

    @patch(
        "app.culling.datetime", **{"now.return_value": datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)}
    )
    def test_query_variables_staleness(self, datetime_mock, graphql_query):
        for staleness, expected in (
            ("fresh", {"gt": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale", {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale_warning", {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
        ):
            with self.subTest(staleness=staleness):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?staleness={staleness}", 200)
                self._assert_graph_query_single_call_with_staleness(graphql_query, (expected,))

    @patch(
        "app.culling.datetime", **{"now.return_value": datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)}
    )
    def test_query_multiple_staleness(self, datetime_mock, graphql_query):

        staleness = "fresh,stale_warning"
        graphql_query.reset_mock()
        self.get(f"{HOST_URL}?staleness={staleness}", 200)
        self._assert_graph_query_single_call_with_staleness(
            graphql_query,
            (
                {"gt": "2019-12-16T10:10:06.754201+00:00"},  # fresh
                {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"},  # stale warning
            ),
        )

    def test_query_variables_staleness_with_search(self, graphql_query):
        for field, value in (
            ("fqdn", generate_uuid()),
            ("display_name", "some display name"),
            ("hostname_or_id", "some hostname"),
            ("insights_id", generate_uuid()),
            ("tags", "some/tag"),
        ):
            with self.subTest(field=field):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?{field}={quote(value)}")

                SEARCH_ANY = ANY
                STALENESS_ANY = ANY
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": (SEARCH_ANY, STALENESS_ANY),
                    },
                )


class HostsXjoinResponseTestCase(HostsXjoinBaseTestCase):
    patch_with_response = partial(patch, "api.host_query_xjoin.graphql_query", return_value=MOCK_XJOIN_HOST_RESPONSE)

    @patch_with_response()
    def test_response_processed_properly(self, graphql_query):
        result = self.get(HOST_URL, 200)
        graphql_query.assert_called_once()

        self.assertEqual(
            result,
            {
                "total": 2,
                "count": 2,
                "page": 1,
                "per_page": 50,
                "results": [
                    {
                        "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                        "account": "test",
                        "display_name": "test01.rhel7.jharting.local",
                        "ansible_host": "test01.rhel7.jharting.local",
                        "created": "2019-02-10T08:07:03.354307+00:00",
                        "updated": "2019-02-10T08:07:03.354312+00:00",
                        "fqdn": "fqdn.test01.rhel7.jharting.local",
                        "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                        "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                        "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                        "reporter": "puptoo",
                        "rhel_machine_id": None,
                        "subscription_manager_id": None,
                        "bios_uuid": None,
                        "ip_addresses": None,
                        "mac_addresses": None,
                        "external_id": None,
                        "stale_warning_timestamp": "2020-02-17T08:07:03.354307+00:00",
                        "culled_timestamp": "2020-02-24T08:07:03.354307+00:00",
                        "facts": [],
                    },
                    {
                        "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                        "account": "test",
                        "display_name": "test02.rhel7.jharting.local",
                        "ansible_host": "test02.rhel7.jharting.local",
                        "created": "2019-01-10T08:07:03.354307+00:00",
                        "updated": "2019-01-10T08:07:03.354312+00:00",
                        "fqdn": "fqdn.test02.rhel7.jharting.local",
                        "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                        "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                        "stale_timestamp": "2020-01-10T08:07:03.354307+00:00",
                        "reporter": "puptoo",
                        "rhel_machine_id": None,
                        "subscription_manager_id": None,
                        "bios_uuid": None,
                        "ip_addresses": None,
                        "mac_addresses": None,
                        "external_id": None,
                        "stale_warning_timestamp": "2020-01-17T08:07:03.354307+00:00",
                        "culled_timestamp": "2020-01-24T08:07:03.354307+00:00",
                        "facts": [
                            {"namespace": "os", "facts": {"os.release": "Red Hat Enterprise Linux Server"}},
                            {
                                "namespace": "bios",
                                "facts": {
                                    "bios.vendor": "SeaBIOS",
                                    "bios.release_date": "2014-04-01",
                                    "bios.version": "1.11.0-2.el7",
                                },
                            },
                        ],
                    },
                ],
            },
        )

    @patch_with_response()
    def test_response_pagination_index_error(self, graphql_query):
        self.get(f"{HOST_URL}?per_page=2&page=3", 404)
        graphql_query.assert_called_once()


class HostsXjoinTimestampsTestCase(HostsXjoinBaseTestCase):
    @staticmethod
    def _xjoin_host_response(timestamp):
        return {
            "hosts": {
                **MOCK_XJOIN_HOST_RESPONSE["hosts"],
                "meta": {"total": 1},
                "data": [
                    {
                        **MOCK_XJOIN_HOST_RESPONSE["hosts"]["data"][0],
                        "created_on": timestamp,
                        "modified_on": timestamp,
                        "stale_timestamp": timestamp,
                    }
                ],
            }
        }

    def test_valid_without_decimal_part(self):
        xjoin_host_response = self._xjoin_host_response("2020-02-10T08:07:03Z")
        with patch("api.host_query_xjoin.graphql_query", return_value=xjoin_host_response):
            get_host_list_response = self.get(HOST_URL, 200)
            retrieved_host = get_host_list_response["results"][0]
            self.assertEqual(retrieved_host["stale_timestamp"], "2020-02-10T08:07:03+00:00")

    def test_valid_with_offset_timezone(self):
        xjoin_host_response = self._xjoin_host_response("2020-02-10T08:07:03.354307+01:00")
        with patch("api.host_query_xjoin.graphql_query", return_value=xjoin_host_response):
            get_host_list_response = self.get(HOST_URL, 200)
            retrieved_host = get_host_list_response["results"][0]
            self.assertEqual(retrieved_host["stale_timestamp"], "2020-02-10T07:07:03.354307+00:00")

    def test_invalid_without_timezone(self):
        xjoin_host_response = self._xjoin_host_response("2020-02-10T08:07:03.354307")
        with patch("api.host_query_xjoin.graphql_query", return_value=xjoin_host_response):
            self.get(HOST_URL, 500)


@patch("api.tag.xjoin_enabled", return_value=True)
class TagsRequestTestCase(XjoinRequestBaseTestCase):
    patch_with_empty_response = partial(
        patch, "api.tag.graphql_query", return_value={"hostTags": {"meta": {"count": 0, "total": 0}, "data": []}}
    )

    def test_headers_forwarded(self, xjoin_enabled):
        value = {"data": {"hostTags": {"meta": {"count": 0, "total": 0}, "data": []}}}
        with self._patch_xjoin_post(value) as resp:
            req_id = "353b230b-5607-4454-90a1-589fbd61fde9"
            self._get_with_request_id(TAGS_URL, req_id)
            self._assert_called_with_headers(resp, req_id)

    @patch_with_empty_response()
    def test_query_variables_default_except_staleness(self, graphql_query, xjoin_enabled):
        self.get(TAGS_URL, 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY, {"order_by": "tag", "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": ANY}}
        )

    @patch_with_empty_response()
    @patch("app.culling.datetime")
    def test_query_variables_default_staleness(self, datetime_mock, graphql_query, xjoin_enabled):
        datetime_mock.now.return_value = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)

        self.get(TAGS_URL, 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "hostFilter": {
                    "OR": [
                        {"stale_timestamp": {"gt": "2019-12-16T10:10:06.754201+00:00"}},
                        {
                            "stale_timestamp": {
                                "gt": "2019-12-09T10:10:06.754201+00:00",
                                "lte": "2019-12-16T10:10:06.754201+00:00",
                            }
                        },
                    ]
                },
            },
        )

    @patch("app.culling.datetime")
    def test_query_variables_staleness(self, datetime_mock, xjoin_enabled):
        now = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
        datetime_mock.now = mock.Mock(return_value=now)

        for staleness, expected in (
            ("fresh", {"gt": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale", {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale_warning", {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
        ):
            with self.subTest(staleness=staleness):
                with self.patch_with_empty_response() as graphql_query:
                    self.get(f"{TAGS_URL}?staleness={staleness}", 200)

                    graphql_query.assert_called_once_with(
                        TAGS_QUERY,
                        {
                            "order_by": "tag",
                            "order_how": "ASC",
                            "limit": 50,
                            "offset": 0,
                            "hostFilter": {"OR": [{"stale_timestamp": expected}]},
                        },
                    )

    @patch("app.culling.datetime")
    def test_multiple_query_variables_staleness(self, datetime_mock, xjoin_enabled):
        now = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
        datetime_mock.now = mock.Mock(return_value=now)

        staleness = "fresh,stale_warning"
        with self.patch_with_empty_response() as graphql_query:
            self.get(f"{TAGS_URL}?staleness={staleness}", 200)

            graphql_query.assert_called_once_with(
                TAGS_QUERY,
                {
                    "order_by": "tag",
                    "order_how": "ASC",
                    "limit": 50,
                    "offset": 0,
                    "hostFilter": {
                        "OR": [
                            {"stale_timestamp": {"gt": "2019-12-16T10:10:06.754201+00:00"}},
                            {
                                "stale_timestamp": {
                                    "gt": "2019-12-02T10:10:06.754201+00:00",
                                    "lte": "2019-12-09T10:10:06.754201+00:00",
                                }
                            },
                        ]
                    },
                },
            )

    @patch_with_empty_response()
    def test_query_variables_tags_simple(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=insights-client/os=fedora", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "OR": ANY,
                    "AND": (
                        {
                            "tag": {
                                "namespace": {"eq": "insights-client"},
                                "key": {"eq": "os"},
                                "value": {"eq": "fedora"},
                            }
                        },
                    ),
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_with_special_characters_unescaped(self, graphql_query, xjoin_enabled):
        tags_query = quote(";?:@&+$/-_.!~*'()=#")
        self.get(f"{TAGS_URL}?tags={tags_query}", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": (
                        {"tag": {"namespace": {"eq": ";?:@&+$"}, "key": {"eq": "-_.!~*'()"}, "value": {"eq": "#"}}},
                    ),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_with_special_characters_escaped(self, graphql_query, xjoin_enabled):
        namespace = quote_everything(";,/?:@&=+$")
        key = quote_everything("-_.!~*'()")
        value = quote_everything("#")
        tags_query = quote(f"{namespace}/{key}={value}")
        self.get(f"{TAGS_URL}?tags={tags_query}", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": (
                        {"tag": {"namespace": {"eq": ";,/?:@&=+$"}, "key": {"eq": "-_.!~*'()"}, "value": {"eq": "#"}}},
                    ),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_collection_multi(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=Sat/env=prod&tags=insights-client/os=fedora", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": (
                        {"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},
                        {
                            "tag": {
                                "namespace": {"eq": "insights-client"},
                                "key": {"eq": "os"},
                                "value": {"eq": "fedora"},
                            }
                        },
                    ),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_collection_csv(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=Sat/env=prod,insights-client/os=fedora", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": (
                        {"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},
                        {
                            "tag": {
                                "namespace": {"eq": "insights-client"},
                                "key": {"eq": "os"},
                                "value": {"eq": "fedora"},
                            }
                        },
                    ),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_without_namespace(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=env=prod", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": ({"tag": {"namespace": {"eq": None}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_without_value(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=Sat/env", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": ({"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": None}}},),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_with_only_key(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=env", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": ({"tag": {"namespace": {"eq": None}, "key": {"eq": "env"}, "value": {"eq": None}}},),
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_search(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?search={quote('Δwithčhar!/~|+ ')}", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "filter": {"search": {"regex": ".*\\Δwith\\čhar\\!\\/\\~\\|\\+\\ .*"}},
                "hostFilter": {"OR": ANY},
            },
        )

    def test_query_variables_ordering_dir(self, xjoin_enabled):
        for direction in ["ASC", "DESC"]:
            with self.subTest(direction=direction):
                with self.patch_with_empty_response() as graphql_query:
                    self.get(f"{TAGS_URL}?order_how={direction}", 200)

                    graphql_query.assert_called_once_with(
                        TAGS_QUERY,
                        {
                            "order_by": "tag",
                            "order_how": direction,
                            "limit": 50,
                            "offset": 0,
                            "hostFilter": {"OR": ANY},
                        },
                    )

    def test_query_variables_ordering_by(self, xjoin_enabled):
        for ordering in ["tag", "count"]:
            with self.patch_with_empty_response() as graphql_query:
                self.get(f"{TAGS_URL}?order_by={ordering}", 200)

                graphql_query.assert_called_once_with(
                    TAGS_QUERY,
                    {"order_by": ordering, "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": ANY}},
                )

    def test_response_pagination(self, xjoin_enabled):
        for page, limit, offset in [(1, 2, 0), (2, 2, 2), (4, 50, 150)]:
            with self.subTest(page=page):
                with self.patch_with_empty_response() as graphql_query:
                    self.get(f"{TAGS_URL}?per_page={limit}&page={page}", 200)

                    graphql_query.assert_called_once_with(
                        TAGS_QUERY,
                        {
                            "order_by": "tag",
                            "order_how": "ASC",
                            "limit": limit,
                            "offset": offset,
                            "hostFilter": {"OR": ANY},
                        },
                    )

    def test_response_invalid_pagination(self, xjoin_enabled):
        for page, per_page in [(0, 10), (-1, 10), (1, 0), (1, -5), (1, 101)]:
            with self.subTest(page=page):
                with self.patch_with_empty_response():
                    self.get(f"{TAGS_URL}?per_page={per_page}&page={page}", 400)

    @patch_with_empty_response()
    def test_query_variables_registered_with(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?registered_with=insights", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "hostFilter": {"OR": ANY, "NOT": {"insights_id": {"eq": None}}},
            },
        )

    def test_response_invalid_registered_with(self, xjoin_enabled):
        self.get(f"{TAGS_URL}?registered_with=salad", 400)


@patch("api.tag.xjoin_enabled", return_value=True)
class TagsResponseTestCase(ApiBaseTestCase):
    RESPONSE = {
        "hostTags": {
            "meta": {"count": 3, "total": 3},
            "data": [
                {"tag": {"namespace": "Sat", "key": "env", "value": "prod"}, "count": 3},
                {"tag": {"namespace": "insights-client", "key": "database", "value": None}, "count": 2},
                {"tag": {"namespace": "insights-client", "key": "os", "value": "fedora"}, "count": 2},
            ],
        }
    }

    patch_with_tags = partial(patch, "api.tag.graphql_query", return_value=RESPONSE)

    @patch_with_tags()
    def test_response_processed_properly(self, graphql_query, xjoin_enabled):
        expected = self.RESPONSE["hostTags"]
        result = self.get(TAGS_URL, 200)
        graphql_query.assert_called_once()

        self.assertEqual(
            result,
            {
                "total": expected["meta"]["total"],
                "count": expected["meta"]["count"],
                "page": 1,
                "per_page": 50,
                "results": expected["data"],
            },
        )

    @patch_with_tags()
    def test_response_pagination_index_error(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?per_page=2&page=3", 404)

        graphql_query.assert_called_once_with(
            TAGS_QUERY, {"order_by": "tag", "order_how": "ASC", "limit": 2, "offset": 4, "hostFilter": {"OR": ANY}}
        )


class XjoinBulkSourceSwitchTestCaseEnvXjoin(DbApiBaseTestCase):
    def setUp(self):
        with set_environment({"BULK_QUERY_SOURCE": "xjoin", "BULK_QUERY_SOURCE_BETA": "db"}):
            super().setUp()

    patch_with_response = partial(patch, "api.host_query_xjoin.graphql_query", return_value=MOCK_XJOIN_HOST_RESPONSE)

    @patch_with_response()
    def test_bulk_source_header_set_to_db(self, graphql_query):  # FAILING
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "db"})
        graphql_query.assert_not_called()

    @patch_with_response()
    def test_bulk_source_header_set_to_xjoin(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "xjoin"})
        graphql_query.assert_called_once()

    @patch_with_response()  # should use db FAILING
    def test_referer_header_set_to_beta(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/beta/something"})
        graphql_query.assert_not_called()

    @patch_with_response()  # should use xjoin
    def test_referer_not_beta(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/something"})
        graphql_query.assert_called_once()

    @patch_with_response()  # should use xjoin
    def test_no_header_env_var_xjoin(self, graphql_query):
        self.get(f"{HOST_URL}", 200)
        graphql_query.assert_called_once()


class XjoinBulkSourceSwitchTestCaseEnvDb(DbApiBaseTestCase):
    def setUp(self):
        with set_environment({"BULK_QUERY_SOURCE": "db", "BULK_QUERY_SOURCE_BETA": "xjoin"}):
            super().setUp()

    patch_with_response = partial(patch, "api.host_query_xjoin.graphql_query", return_value=MOCK_XJOIN_HOST_RESPONSE)

    @patch_with_response()
    def test_bulk_source_header_set_to_db(self, graphql_query):  # FAILING
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "db"})
        graphql_query.assert_not_called()

    @patch_with_response()
    def test_bulk_source_header_set_to_xjoin(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "xjoin"})
        graphql_query.assert_called_once()

    @patch_with_response()
    def test_referer_not_beta(self, graphql_query):  # should use db FAILING
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/something"})
        graphql_query.assert_not_called()

    @patch_with_response()  # should use xjoin
    def test_referer_header_set_to_beta(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/beta/something"})
        graphql_query.assert_called_once()

    @patch_with_response()  # should use db FAILING
    def test_no_header_env_var_db(self, graphql_query):
        self.get(f"{HOST_URL}", 200)
        graphql_query.assert_not_called()


if __name__ == "__main__":
    main()
