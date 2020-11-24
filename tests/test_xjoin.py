from re import escape

import pytest

from api.host_query_xjoin import QUERY as HOST_QUERY
from api.system_profile import SAP_SIDS_QUERY
from api.system_profile import SAP_SYSTEM_QUERY
from api.tag import TAGS_QUERY
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import quote
from tests.helpers.api_utils import quote_everything
from tests.helpers.api_utils import READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import TAGS_URL
from tests.helpers.graphql_utils import assert_called_with_headers
from tests.helpers.graphql_utils import assert_graph_query_single_call_with_staleness
from tests.helpers.graphql_utils import EMPTY_HOSTS_RESPONSE
from tests.helpers.graphql_utils import TAGS_EMPTY_RESPONSE
from tests.helpers.graphql_utils import xjoin_host_response
from tests.helpers.graphql_utils import XJOIN_TAGS_RESPONSE
from tests.helpers.test_utils import generate_uuid


def test_headers_forwarded(mocker, patch_xjoin_post, api_get):
    post = patch_xjoin_post({"data": EMPTY_HOSTS_RESPONSE})

    request_id = generate_uuid()
    response_status, response_data = api_get(
        HOST_URL, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"}
    )

    assert response_status == 200

    assert_called_with_headers(mocker, post, request_id)


def test_host_request_xjoin_status_403(patch_xjoin_post, api_get):
    patch_xjoin_post(response={"data": EMPTY_HOSTS_RESPONSE}, status=403)
    request_id = generate_uuid()

    response_status, response_data = api_get(
        HOST_URL, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"}
    )

    assert response_status == 500


def test_host_request_xjoin_status_200(patch_xjoin_post, api_get):
    patch_xjoin_post(response={"data": EMPTY_HOSTS_RESPONSE}, status=200)
    request_id = generate_uuid()

    response_status, response_data = api_get(
        HOST_URL, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"}
    )

    assert response_status == 200


def test_query_variables_fqdn(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    fqdn = "host.domain.com"

    url = build_hosts_url(query=f"?fqdn={quote(fqdn)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"fqdn": {"eq": fqdn}}, mocker.ANY),
        },
    )


def test_query_variables_display_name(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    display_name = "my awesome host uwu"

    url = build_hosts_url(query=f"?display_name={quote(display_name)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"display_name": {"matches_lc": f"*{display_name}*"}}, mocker.ANY),
        },
    )


def test_query_variables_hostname_or_id_non_uuid(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    hostname_or_id = "host.domain.com"

    url = build_hosts_url(query=f"?hostname_or_id={quote(hostname_or_id)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (
                {
                    "OR": (
                        {"display_name": {"matches_lc": f"*{hostname_or_id}*"}},
                        {"fqdn": {"matches": f"*{hostname_or_id}*"}},
                    )
                },
                mocker.ANY,
            ),
        },
    )


def test_query_variables_hostname_or_id_uuid(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    hostname_or_id = generate_uuid()

    url = build_hosts_url(query=f"?hostname_or_id={quote(hostname_or_id)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (
                {
                    "OR": (
                        {"display_name": {"matches_lc": f"*{hostname_or_id}*"}},
                        {"fqdn": {"matches": f"*{hostname_or_id}*"}},
                        {"id": {"eq": hostname_or_id}},
                    )
                },
                mocker.ANY,
            ),
        },
    )


def test_query_variables_insights_id(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    insights_id = generate_uuid()

    url = build_hosts_url(query=f"?insights_id={quote(insights_id)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"insights_id": {"eq": insights_id}}, mocker.ANY),
        },
    )


def test_query_variables_none(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (mocker.ANY,),
        },
    )


@pytest.mark.parametrize(
    "filter_,query",
    (
        ("fqdn", f"fqdn={quote(generate_uuid())}&display_name={quote(generate_uuid())}"),
        ("fqdn", f"fqdn={quote(generate_uuid())}&hostname_or_id={quote(generate_uuid())}"),
        ("fqdn", f"fqdn={quote(generate_uuid())}&insights_id={quote(generate_uuid())}"),
        ("display_name", f"display_name={quote(generate_uuid())}&hostname_or_id={quote(generate_uuid())}"),
        ("display_name", f"display_name={quote(generate_uuid())}&insights_id={quote(generate_uuid())}"),
        ("OR", f"hostname_or_id={quote(generate_uuid())}&insights_id={quote(generate_uuid())}"),
    ),
)
def test_query_variables_priority(filter_, query, mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?{query}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({filter_: mocker.ANY}, mocker.ANY),
        },
    )


@pytest.mark.parametrize(
    "tags,query_param",
    (
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
    ),
)
def test_query_variables_tags(tags, query_param, mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?tags={quote(query_param)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    tag_filters = tuple({"tag": item} for item in tags)

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": tag_filters + (mocker.ANY,),
        },
    )


@pytest.mark.parametrize("field", ("fqdn", "display_name", "hostname_or_id", "insights_id"))
def test_query_variables_tags_with_search(field, mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    value = quote(generate_uuid())

    url = build_hosts_url(query=f"?{field}={value}&tags=a/b=c")
    response_status, response_data = api_get(url)

    assert response_status == 200

    search_any = mocker.ANY
    tag_filter = {"tag": {"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}}}

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (search_any, tag_filter, mocker.ANY),
        },
    )


def test_query_variables_registered_with_insights(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?registered_with=insights")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (mocker.ANY, {"NOT": {"insights_id": {"eq": None}}}),
        },
    )


@pytest.mark.parametrize("direction", ("ASC", "DESC"))
def test_query_variables_ordering_dir(direction, mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?order_by=updated&order_how={quote(direction)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "order_by": mocker.ANY,
            "order_how": direction,
            "filter": mocker.ANY,
        },
    )


@pytest.mark.parametrize(
    "params_order_by,xjoin_order_by,default_xjoin_order_how",
    (("updated", "modified_on", "DESC"), ("display_name", "display_name", "ASC")),
)
def test_query_variables_ordering_by(
    params_order_by,
    xjoin_order_by,
    default_xjoin_order_how,
    mocker,
    query_source_xjoin,
    graphql_query_empty_response,
    api_get,
):
    url = build_hosts_url(query=f"?order_by={quote(params_order_by)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "order_by": xjoin_order_by,
            "order_how": default_xjoin_order_how,
            "filter": mocker.ANY,
        },
    )


def test_query_variables_ordering_by_invalid(query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?order_by=fqdn")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_ordering_dir_invalid(query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?order_by=updated&order_how=REVERSE")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_ordering_dir_without_by(query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


@pytest.mark.parametrize("page,limit,offset", ((1, 2, 0), (2, 2, 2), (4, 50, 150)))
def test_response_pagination(page, limit, offset, mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?per_page={quote(limit)}&page={quote(page)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {"order_by": mocker.ANY, "order_how": mocker.ANY, "limit": limit, "offset": offset, "filter": mocker.ANY},
    )


@pytest.mark.parametrize("page,per_page", ((0, 10), (-1, 10), (1, 0), (1, -5), (1, 101)))
def test_response_invalid_pagination(page, per_page, query_source_xjoin, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?per_page={quote(per_page)}&page={quote(page)}")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_default_except_staleness(mocker, query_source_xjoin, graphql_query_empty_response, api_get):
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY, {"order_by": "modified_on", "order_how": "DESC", "limit": 50, "offset": 0, "filter": mocker.ANY}
    )


def test_query_variables_default_staleness(
    mocker, culling_datetime_mock, query_source_xjoin, graphql_query_empty_response, api_get
):
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    assert_graph_query_single_call_with_staleness(
        mocker,
        graphql_query_empty_response,
        (
            {"gt": "2019-12-16T10:10:06.754201+00:00"},  # fresh
            {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"},  # stale
        ),
    )


@pytest.mark.parametrize(
    "staleness,expected",
    (
        ("fresh", {"gt": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale", {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale_warning", {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
    ),
)
def test_query_variables_staleness(
    staleness, expected, mocker, culling_datetime_mock, query_source_xjoin, graphql_query_empty_response, api_get
):
    url = build_hosts_url(query=f"?staleness={staleness}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    assert_graph_query_single_call_with_staleness(mocker, graphql_query_empty_response, (expected,))


def test_query_multiple_staleness(
    mocker, culling_datetime_mock, query_source_xjoin, graphql_query_empty_response, api_get
):
    staleness = "fresh,stale_warning"

    url = build_hosts_url(query=f"?staleness={staleness}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    assert_graph_query_single_call_with_staleness(
        mocker,
        graphql_query_empty_response,
        (
            {"gt": "2019-12-16T10:10:06.754201+00:00"},  # fresh
            {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"},  # stale warning
        ),
    )


@pytest.mark.parametrize(
    "field,value",
    (
        ("fqdn", generate_uuid()),
        ("display_name", "some display name"),
        ("hostname_or_id", "some hostname"),
        ("insights_id", generate_uuid()),
        ("tags", "some/tag"),
    ),
)
def test_query_variables_staleness_with_search(
    field, value, mocker, culling_datetime_mock, query_source_xjoin, graphql_query_empty_response, api_get
):
    url = build_hosts_url(query=f"?{field}={quote(value)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    search_any = mocker.ANY
    staleness_any = mocker.ANY

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (search_any, staleness_any),
        },
    )


def test_response_processed_properly(query_source_xjoin, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    graphql_query_with_response.assert_called_once()

    assert response_data == {
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
    }


def test_response_pagination_index_error(query_source_xjoin, graphql_query_with_response, api_get):
    url = build_hosts_url(query="?per_page=2&page=3")
    response_status, response_data = api_get(url)

    assert response_status == 404

    graphql_query_with_response.assert_called_once()


def test_valid_without_decimal_part(query_source_xjoin, graphql_query, api_get):
    response = xjoin_host_response("2020-02-10T08:07:03Z")

    graphql_query(return_value=response)
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200
    assert response_data["results"][0]["stale_timestamp"] == "2020-02-10T08:07:03+00:00"


def test_valid_with_offset_timezone(query_source_xjoin, graphql_query, api_get):
    response = xjoin_host_response("2020-02-10T08:07:03.354307+01:00")

    graphql_query(return_value=response)
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200
    assert response_data["results"][0]["stale_timestamp"] == "2020-02-10T07:07:03.354307+00:00"


def test_invalid_without_timezone(query_source_xjoin, graphql_query, api_get):
    response = xjoin_host_response("2020-02-10T08:07:03.354307")

    graphql_query(return_value=response)
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 500


def test_tags_headers_forwarded(mocker, patch_xjoin_post, api_get):
    post = patch_xjoin_post({"data": TAGS_EMPTY_RESPONSE})

    request_id = generate_uuid()
    response_status, response_data = api_get(
        TAGS_URL, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"}
    )

    assert response_status == 200

    assert_called_with_headers(mocker, post, request_id)


def test_tags_query_variables_default_except_staleness(
    mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    response_status, response_data = api_get(TAGS_URL)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY, {"order_by": "tag", "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": mocker.ANY}}
    )


def test_tags_query_variables_default_staleness(
    mocker, culling_datetime_mock, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    response_status, response_data = api_get(TAGS_URL)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
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


@pytest.mark.parametrize(
    "staleness,expected",
    (
        ("fresh", {"gt": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale", {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale_warning", {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
    ),
)
def test_tags_query_variables_staleness(
    staleness, expected, culling_datetime_mock, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    url = build_tags_url(query=f"?staleness={staleness}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {"OR": [{"stale_timestamp": expected}]},
        },
    )


def test_tags_multiple_query_variables_staleness(
    culling_datetime_mock, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    staleness = "fresh,stale_warning"
    url = build_tags_url(query=f"?staleness={staleness}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
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


def test_query_variables_tags_simple(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?tags=insights-client/os=fedora")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "OR": mocker.ANY,
                "AND": (
                    {"tag": {"namespace": {"eq": "insights-client"}, "key": {"eq": "os"}, "value": {"eq": "fedora"}}},
                ),
            },
        },
    )


def test_query_variables_tags_with_special_characters_unescaped(
    mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    tags_query = quote(";?:@&+$/-_.!~*'()=#")
    url = build_tags_url(query=f"?tags={tags_query}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "AND": ({"tag": {"namespace": {"eq": ";?:@&+$"}, "key": {"eq": "-_.!~*'()"}, "value": {"eq": "#"}}},),
                "OR": mocker.ANY,
            },
        },
    )


def test_query_variables_tags_with_special_characters_escaped(
    mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    namespace = quote_everything(";,/?:@&=+$")
    key = quote_everything("-_.!~*'()")
    value = quote_everything("#")
    tags_query = quote(f"{namespace}/{key}={value}")

    url = build_tags_url(query=f"?tags={tags_query}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
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
                "OR": mocker.ANY,
            },
        },
    )


def test_query_variables_tags_collection_multi(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?tags=Sat/env=prod&tags=insights-client/os=fedora")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "AND": (
                    {"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},
                    {"tag": {"namespace": {"eq": "insights-client"}, "key": {"eq": "os"}, "value": {"eq": "fedora"}}},
                ),
                "OR": mocker.ANY,
            },
        },
    )


def test_query_variables_tags_collection_csv(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?tags=Sat/env=prod,insights-client/os=fedora")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "AND": (
                    {"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},
                    {"tag": {"namespace": {"eq": "insights-client"}, "key": {"eq": "os"}, "value": {"eq": "fedora"}}},
                ),
                "OR": mocker.ANY,
            },
        },
    )


def test_query_variables_tags_without_namespace(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?tags=env=prod")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "AND": ({"tag": {"namespace": {"eq": None}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},),
                "OR": mocker.ANY,
            },
        },
    )


def test_query_variables_tags_without_value(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?tags=Sat/env")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "AND": ({"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": None}}},),
                "OR": mocker.ANY,
            },
        },
    )


def test_query_variables_tags_with_only_key(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?tags=env")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "hostFilter": {
                "AND": ({"tag": {"namespace": {"eq": None}, "key": {"eq": "env"}, "value": {"eq": None}}},),
                "OR": mocker.ANY,
            },
        },
    )


def test_tags_query_variables_search(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    query = "Δwithčhar!/~|+ "
    url = build_tags_url(query=f"?search={quote(query)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": "tag",
            "order_how": "ASC",
            "limit": 50,
            "offset": 0,
            "filter": {"search": {"regex": f".*{escape(query)}.*"}},
            "hostFilter": {"OR": mocker.ANY},
        },
    )


@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_tags_query_variables_ordering_dir(
    direction, mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    url = build_tags_url(query=f"?order_how={direction}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": "tag", "order_how": direction, "limit": 50, "offset": 0, "hostFilter": {"OR": mocker.ANY}},
    )


@pytest.mark.parametrize("ordering", ["tag", "count"])
def test_tags_query_variables_ordering_by(
    ordering, mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    url = build_tags_url(query=f"?order_by={ordering}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": ordering, "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": mocker.ANY}},
    )


@pytest.mark.parametrize("page,limit,offset", [(1, 2, 0), (2, 2, 2), (4, 50, 150)])
def test_tags_response_pagination(
    page, limit, offset, mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    url = build_tags_url(query=f"?per_page={limit}&page={page}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": "tag", "order_how": "ASC", "limit": limit, "offset": offset, "hostFilter": {"OR": mocker.ANY}},
    )


@pytest.mark.parametrize("page,per_page", [(0, 10), (-1, 10), (1, 0), (1, -5), (1, 101)])
def test_tags_response_invalid_pagination(page, per_page, api_get):
    url = build_tags_url(query=f"?per_page={per_page}&page={page}")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_tags_query_variables_registered_with(mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query="?registered_with=insights")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "hostFilter": {"OR": mocker.ANY, "NOT": {"insights_id": {"eq": None}}},
        },
    )


def test_tags_response_invalid_registered_with(api_get):
    url = build_tags_url(query="?registered_with=salad")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_tags_response_processed_properly(query_source_xjoin, graphql_tag_query_with_response, api_get):
    expected = XJOIN_TAGS_RESPONSE["hostTags"]

    response_status, response_data = api_get(TAGS_URL)

    assert response_status == 200

    graphql_tag_query_with_response.assert_called_once()

    assert response_data == {
        "total": expected["meta"]["total"],
        "count": expected["meta"]["count"],
        "page": 1,
        "per_page": 50,
        "results": expected["data"],
    }


def test_tags_response_pagination_index_error(mocker, query_source_xjoin, graphql_tag_query_with_response, api_get):
    url = build_tags_url(query="?per_page=2&page=3")
    response_status, response_data = api_get(url)

    assert response_status == 404

    graphql_tag_query_with_response.assert_called_once_with(
        TAGS_QUERY, {"order_by": "tag", "order_how": "ASC", "limit": 2, "offset": 4, "hostFilter": {"OR": mocker.ANY}}
    )


def test_tags_RBAC_allowed(
    subtests, mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_url(query="?registered_with=insights")
            response_status, response_data = api_get(url)

            assert response_status == 200


def test_tags_RBAC_denied(
    subtests, mocker, query_source_xjoin, graphql_tag_query_empty_response, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_url(query="?registered_with=insights")
            response_status, response_data = api_get(url)

            assert response_status == 403

            graphql_tag_query_empty_response.assert_not_called()


def test_bulk_source_header_set_to_db(query_source_xjoin_beta_db, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL, extra_headers={"x-rh-cloud-bulk-query-source": "db"})
    assert response_status == 200
    graphql_query_with_response.assert_not_called()


def test_bulk_source_header_set_to_xjoin(query_source_xjoin_beta_db, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL, extra_headers={"x-rh-cloud-bulk-query-source": "xjoin"})
    assert response_status == 200
    graphql_query_with_response.assert_called_once()


def test_referer_header_set_to_beta(query_source_xjoin_beta_db, graphql_query_with_response, api_get):
    response_status, response_data = api_get(
        HOST_URL, extra_headers={"referer": "http://www.cloud.redhat.com/beta/something"}
    )
    assert response_status == 200
    graphql_query_with_response.assert_not_called()


def test_referer_not_beta(query_source_xjoin_beta_db, graphql_query_with_response, api_get):
    response_status, response_data = api_get(
        HOST_URL, extra_headers={"referer": "http://www.cloud.redhat.com/something"}
    )
    assert response_status == 200
    graphql_query_with_response.assert_called_once()


def test_no_header_env_var_xjoin(query_source_xjoin_beta_db, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL)
    assert response_status == 200
    graphql_query_with_response.assert_called_once()


def test_bulk_source_header_set_to_db_2(query_source_db_beta_xjoin, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL, extra_headers={"x-rh-cloud-bulk-query-source": "db"})
    assert response_status == 200
    graphql_query_with_response.assert_not_called()


def test_bulk_source_header_set_to_xjoin_2(query_source_db_beta_xjoin, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL, extra_headers={"x-rh-cloud-bulk-query-source": "xjoin"})
    assert response_status == 200
    graphql_query_with_response.assert_called_once()


def test_referer_not_beta_2(query_source_db_beta_xjoin, graphql_query_with_response, api_get):
    response_status, response_data = api_get(
        HOST_URL, extra_headers={"referer": "http://www.cloud.redhat.com/something"}
    )
    assert response_status == 200
    graphql_query_with_response.assert_not_called()


def test_referer_header_set_to_beta_2(query_source_db_beta_xjoin, graphql_query_with_response, api_get):
    response_status, response_data = api_get(
        HOST_URL, extra_headers={"referer": "http://www.cloud.redhat.com/beta/something"}
    )
    assert response_status == 200
    graphql_query_with_response.assert_called_once()


def test_no_header_env_var_db(inventory_config, query_source_db_beta_xjoin, graphql_query_with_response, api_get):
    response_status, response_data = api_get(HOST_URL)
    assert response_status == 200
    graphql_query_with_response.assert_not_called()


def test_system_profile_sap_system_endpoint(
    mocker, query_source_xjoin, graphql_system_profile_sap_system_query_empty_response, api_get
):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY}}
    )


@pytest.mark.parametrize(
    "tags,query_param",
    (
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
    ),
)
def test_system_profile_sap_system_endpoint_tags(
    tags, query_param, mocker, query_source_xjoin, graphql_system_profile_sap_system_query_empty_response, api_get
):
    url = build_system_profile_sap_system_url(query=f"?tags={quote(query_param)}")

    response_status, response_data = api_get(url)

    tag_filters = tuple({"tag": item} for item in tags)
    assert response_status == 200
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY, "AND": tag_filters}}
    )


def test_system_profile_sap_system_endpoint_registered_with_insights(
    mocker, query_source_xjoin, graphql_system_profile_sap_system_query_empty_response, api_get
):
    url = build_system_profile_sap_system_url(query="?registered_with=insights")

    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY, "NOT": {"insights_id": {"eq": None}}}}
    )


def test_system_profile_sap_sids_endpoint(
    mocker, query_source_xjoin, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY}}
    )


@pytest.mark.parametrize(
    "tags,query_param",
    (
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
    ),
)
def test_system_profile_sap_sids_endpoint_tags(
    tags, query_param, mocker, query_source_xjoin, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    url = build_system_profile_sap_sids_url(query=f"?tags={quote(query_param)}")

    response_status, response_data = api_get(url)

    tag_filters = tuple({"tag": item} for item in tags)
    assert response_status == 200
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY, "AND": tag_filters}}
    )


def test_system_profile_sap_sids_endpoint_registered_with_insights(
    mocker, query_source_xjoin, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    url = build_system_profile_sap_sids_url(query="?registered_with=insights")

    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY, "NOT": {"insights_id": {"eq": None}}}}
    )


def test_query_hosts_filter_spf_sap_system(
    mocker, subtests, query_source_xjoin, graphql_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][sap_system]", "[system_profile][sap_system][eq]")
    values = ("true", "false", "nil", "not_nil")
    queries = (
        {"spf_sap_system": {"is": True}},
        {"spf_sap_system": {"is": False}},
        {"spf_sap_system": {"is": None}},
        {"NOT": {"spf_sap_system": {"is": None}}},
    )

    for path in filter_paths:
        for value, query in zip(values, queries):
            with subtests.test(value=value, query=query, path=path):
                url = build_hosts_url(query=f"?filter{path}={value}")

                response_status, response_data = api_get(url)

                assert response_status == 200

                graphql_query_empty_response.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": mocker.ANY,
                        "order_how": mocker.ANY,
                        "limit": mocker.ANY,
                        "offset": mocker.ANY,
                        "filter": ({"OR": mocker.ANY}, query),
                    },
                )
                graphql_query_empty_response.reset_mock()


def test_query_tags_filter_spf_sap_system(
    mocker, subtests, query_source_xjoin, graphql_tag_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][sap_system]", "[system_profile][sap_system][eq]")
    values = ("true", "false", "nil", "not_nil")
    queries = (
        ({"spf_sap_system": {"is": True}},),
        ({"spf_sap_system": {"is": False}},),
        ({"spf_sap_system": {"is": None}},),
        ({"NOT": {"spf_sap_system": {"is": None}}},),
    )

    for path in filter_paths:
        for value, query in zip(values, queries):
            with subtests.test(value=value, query=query, path=path):
                graphql_tag_query_empty_response.reset_mock()
                url = build_tags_url(query=f"?filter{path}={value}")

                response_status, response_data = api_get(url)

                assert response_status == 200

                graphql_tag_query_empty_response.assert_called_once_with(
                    TAGS_QUERY,
                    {
                        "order_by": mocker.ANY,
                        "order_how": mocker.ANY,
                        "limit": mocker.ANY,
                        "offset": mocker.ANY,
                        "hostFilter": {"OR": mocker.ANY, "AND": query},
                    },
                )


def test_query_system_profile_sap_system_filter_spf_sap_sids(
    mocker, subtests, query_source_xjoin, graphql_system_profile_sap_system_query_empty_response, api_get
):
    filter_paths = ("[system_profile][sap_system]", "[system_profile][sap_system][eq]")
    values = ("true", "false", "nil", "not_nil")
    queries = (
        ({"spf_sap_system": {"is": True}},),
        ({"spf_sap_system": {"is": False}},),
        ({"spf_sap_system": {"is": None}},),
        ({"NOT": {"spf_sap_system": {"is": None}}},),
    )

    for path in filter_paths:
        for value, query in zip(values, queries):
            with subtests.test(value=value, query=query, path=path):
                graphql_system_profile_sap_system_query_empty_response.reset_mock()
                url = build_system_profile_sap_system_url(query=f"?filter{path}={value}")

                response_status, response_data = api_get(url)

                assert response_status == 200

                graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
                    SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY, "AND": query}}
                )


def test_query_hosts_filter_spf_sap_sids(mocker, subtests, query_source_xjoin, graphql_query_empty_response, api_get):
    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("XQC",), ("ABC", "A12"), ("M80", "BEN"))
    queries = (
        ({"spf_sap_sids": {"eq": "XQC"}},),
        ({"spf_sap_sids": {"eq": "ABC"}}, {"spf_sap_sids": {"eq": "A12"}}),
        ({"spf_sap_sids": {"eq": "M80"}}, {"spf_sap_sids": {"eq": "BEN"}}),
    )

    for path in filter_paths:
        for values, query in zip(value_sets, queries):
            with subtests.test(values=values, query=query, path=path):
                graphql_query_empty_response.reset_mock()
                url = build_hosts_url(query="?" + "".join([f"filter{path}={value}&" for value in values]))

                response_status, response_data = api_get(url)

                assert response_status == 200

                graphql_query_empty_response.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": mocker.ANY,
                        "order_how": mocker.ANY,
                        "limit": mocker.ANY,
                        "offset": mocker.ANY,
                        "filter": ({"OR": mocker.ANY}, *query),
                    },
                )


def test_query_tags_filter_spf_sap_sids(
    mocker, subtests, query_source_xjoin, graphql_tag_query_empty_response, api_get
):
    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("XQC",), ("ABC", "A12"), ("M80", "BEN"))
    queries = (
        ({"spf_sap_sids": {"eq": "XQC"}},),
        ({"spf_sap_sids": {"eq": "ABC"}}, {"spf_sap_sids": {"eq": "A12"}}),
        ({"spf_sap_sids": {"eq": "M80"}}, {"spf_sap_sids": {"eq": "BEN"}}),
    )

    for path in filter_paths:
        for values, query in zip(value_sets, queries):
            with subtests.test(values=values, query=query, path=path):
                url = build_tags_url(query="?" + "".join([f"filter{path}={value}&" for value in values]))

                response_status, response_data = api_get(url)

                assert response_status == 200

                graphql_tag_query_empty_response.assert_called_once_with(
                    TAGS_QUERY,
                    {
                        "order_by": mocker.ANY,
                        "order_how": mocker.ANY,
                        "limit": mocker.ANY,
                        "offset": mocker.ANY,
                        "hostFilter": {"OR": mocker.ANY, "AND": query},
                    },
                )
                graphql_tag_query_empty_response.reset_mock()


def test_query_system_profile_sap_sids_filter_spf_sap_sids(
    mocker, subtests, query_source_xjoin, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("XQC",), ("ABC", "A12"), ("M80", "BEN"))
    queries = (
        ({"spf_sap_sids": {"eq": "XQC"}},),
        ({"spf_sap_sids": {"eq": "ABC"}}, {"spf_sap_sids": {"eq": "A12"}}),
        ({"spf_sap_sids": {"eq": "M80"}}, {"spf_sap_sids": {"eq": "BEN"}}),
    )

    for path in filter_paths:
        for values, query in zip(value_sets, queries):
            with subtests.test(values=values, query=query, path=path):
                graphql_system_profile_sap_sids_query_empty_response.reset_mock()

                url = build_system_profile_sap_sids_url(
                    query="?" + "".join([f"filter{path}={value}&" for value in values])
                )

                response_status, response_data = api_get(url)

                assert response_status == 200

                graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
                    SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY, "AND": query}}
                )


def test_query_system_profile_sap_sids_with_search(
    mocker, subtests, query_source_xjoin, graphql_system_profile_sap_sids_query_with_response, api_get
):
    url = build_system_profile_sap_sids_url(query="?search=C2")

    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_system_profile_sap_sids_query_with_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY}, "filter": {"search": {"regex": ".*C2.*"}}}
    )
