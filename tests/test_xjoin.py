import pytest

from api import custom_escape
from api.host_query_xjoin import HOST_IDS_QUERY
from api.host_query_xjoin import QUERY as HOST_QUERY
from api.sparse_host_list_system_profile import SYSTEM_PROFILE_SPARSE_QUERY
from api.system_profile import SAP_SIDS_QUERY
from api.system_profile import SAP_SYSTEM_QUERY
from api.tag import TAGS_QUERY
from app import process_spec
from app.models import ProviderType
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_system_profile_url
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
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE_FOR_FILTERING
from tests.helpers.graphql_utils import XJOIN_TAGS_RESPONSE
from tests.helpers.system_profile_utils import system_profile_deep_object_spec
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import SATELLITE_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY


OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]


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


@pytest.mark.parametrize("response_data", (None, {}))
def test_host_request_xjoin_invalid_response(patch_xjoin_post, api_get, response_data):
    patch_xjoin_post(response={"data": response_data}, status=200)
    request_id = generate_uuid()

    response_status, response_data = api_get(
        HOST_URL, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"}
    )

    assert response_status == 503


def test_host_request_xjoin_status_200(patch_xjoin_post, api_get):
    patch_xjoin_post(response={"data": EMPTY_HOSTS_RESPONSE}, status=200)
    request_id = generate_uuid()

    response_status, response_data = api_get(
        HOST_URL, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"}
    )

    assert response_status == 200


def test_query_all_hosts(mocker, graphql_query_empty_response, api_get):
    url = build_hosts_url()
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
                        {"stale_timestamp": mocker.ANY},
                        {"stale_timestamp": mocker.ANY},
                        {"stale_timestamp": mocker.ANY},
                    )
                },
            ),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_fqdn(mocker, graphql_query_empty_response, api_get):
    fqdn = "host.DOMAIN.com"

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
            "filter": ({"fqdn": {"eq": fqdn.casefold()}}, mocker.ANY),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_display_name(mocker, graphql_query_empty_response, api_get):
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_hostname_or_id_non_uuid(mocker, graphql_query_empty_response, api_get):
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
                        {"fqdn": {"matches_lc": f"*{hostname_or_id}*"}},
                    )
                },
                mocker.ANY,
            ),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_hostname_or_id_uuid(mocker, graphql_query_empty_response, api_get):
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
                        {"fqdn": {"matches_lc": f"*{hostname_or_id}*"}},
                        {"id": {"eq": hostname_or_id}},
                    )
                },
                mocker.ANY,
            ),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_insights_id(mocker, graphql_query_empty_response, api_get):
    insights_id = generate_uuid().upper()

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
            "filter": ({"insights_id": {"eq": insights_id.casefold()}}, mocker.ANY),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize("provider_type", ("alibaba", "aws", "azure", "gcp", "ibm"))
def test_query_variables_provider_type(mocker, graphql_query_empty_response, api_get, provider_type):
    url = build_hosts_url(query=f"?provider_type={provider_type}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (mocker.ANY, {"provider_type": {"eq": provider_type}}),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_provider_id(mocker, graphql_query_empty_response, api_get):
    provider_id = generate_uuid()

    url = build_hosts_url(query=f"?provider_id={quote(provider_id)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (mocker.ANY, {"provider_id": {"eq": provider_id}}),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize(
    "provider",
    (
        {"type": "alibaba", "id": generate_uuid()},
        {"type": "aws", "id": "i-05d2313e6b9a42b16"},
        {"type": "azure", "id": generate_uuid()},
        {"type": "gcp", "id": generate_uuid()},
        {"type": "ibm", "id": generate_uuid()},
    ),
)
def test_query_variables_provider_type_and_id(mocker, graphql_query_empty_response, api_get, provider):
    url = build_hosts_url(query=f'?provider_type={provider["type"]}&provider_id={provider["id"]}')
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
                mocker.ANY,
                {"provider_type": {"eq": provider["type"]}},
                {"provider_id": {"eq": provider["id"]}},
            ),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize("provider_type", ("invalid", " ", "\t"))
def test_query_using_invalid_provider_type(mocker, graphql_query_empty_response, api_get, provider_type):
    url = build_hosts_url(query=f"?provider_type={provider_type}")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_none(mocker, graphql_query_empty_response, api_get):
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize(
    "query",
    (
        (f"fqdn={quote(generate_uuid())}&display_name={quote(generate_uuid())}"),
        (f"fqdn={quote(generate_uuid())}&hostname_or_id={quote(generate_uuid())}"),
        (f"fqdn={quote(generate_uuid())}&insights_id={quote(generate_uuid())}"),
        (f"display_name={quote(generate_uuid())}&hostname_or_id={quote(generate_uuid())}"),
        (f"display_name={quote(generate_uuid())}&insights_id={quote(generate_uuid())}"),
        (f"hostname_or_id={quote(generate_uuid())}&insights_id={quote(generate_uuid())}"),
    ),
)
def test_query_variables_invalid(query, mocker, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?{query}")
    response_status, response_data = api_get(url)

    assert response_status == 400


@pytest.mark.parametrize(
    "tags,query_param",
    (
        (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},), f"?tags={quote('a/b=c')}"),
        (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": None}},), f"?tags={quote('a/b')}"),
        (
            (
                {"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},
                {"namespace": {"eq": "d"}, "key": {"eq": "e"}, "value": {"eq": "f"}},
            ),
            f"?tags={quote('a/b=c')}&tags={quote('d/e=f')}",
        ),
        (
            ({"namespace": {"eq": "a/a=a"}, "key": {"eq": "b/b=b"}, "value": {"eq": "c/c=c"}},),
            "?tags=" + quote(quote("a/a=a") + "/" + quote("b/b=b") + "=" + quote("c/c=c")),
        ),
        (({"namespace": {"eq": "ɑ"}, "key": {"eq": "β"}, "value": {"eq": "ɣ"}},), f"?tags={quote('ɑ/β=ɣ')}"),
    ),
)
def test_query_variables_tags(tags, query_param, mocker, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"{query_param}")
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize("field", ("fqdn", "display_name", "hostname_or_id", "insights_id"))
def test_query_variables_tags_with_search(field, mocker, graphql_query_empty_response, api_get):
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


# Build the expected PRS filter based on reporters
def _build_prs_array(mocker, reporters):
    prs_array = []
    for reporter in reporters:
        prs_item = {
            "per_reporter_staleness": {
                "reporter": {"eq": reporter.replace("!", "")},
                "stale_timestamp": {"gt": mocker.ANY},
            }
        }

        if reporter.startswith("!"):
            prs_item = {"NOT": prs_item}

        prs_array.append(prs_item)

    return prs_array


@pytest.mark.parametrize(
    "reporters",
    (
        ["cloud-connector"],
        ["puptoo", "yupana"],
        ["cloud-connector", "puptoo", "rhsm-conduit"],
        ["!puptoo"],
        ["!yupana", "puptoo"],
        ["!yupana", "!puptoo", "rhsm-conduit"],
    ),
)
def test_query_variables_registered_with_per_reporter(mocker, graphql_query_empty_response, api_get, reporters):
    url = build_hosts_url(query="?" + "&".join([f"registered_with={reporter}" for reporter in reporters]))

    response_status, response_data = api_get(url)

    assert response_status == 200

    prs_array = _build_prs_array(mocker, reporters)

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": (
                {"OR": mocker.ANY},
                {"OR": prs_array},
            ),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize("direction", ("ASC", "DESC"))
def test_query_variables_ordering_dir(direction, mocker, graphql_query_empty_response, api_get):
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize(
    "params_order_by,xjoin_order_by,default_xjoin_order_how",
    (
        ("updated", "modified_on", "DESC"),
        ("display_name", "display_name", "ASC"),
        ("operating_system", "operating_system", "DESC"),
    ),
)
def test_query_variables_ordering_by(
    params_order_by, xjoin_order_by, default_xjoin_order_how, mocker, graphql_query_empty_response, api_get
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_ordering_by_invalid(graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?order_by=fqdn")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_ordering_dir_invalid(graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?order_by=updated&order_how=REVERSE")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_ordering_dir_without_by(graphql_query_empty_response, api_get):
    url = build_hosts_url(query="?order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


@pytest.mark.parametrize("page,limit,offset", ((1, 2, 0), (2, 2, 2), (4, 50, 150)))
def test_response_pagination(page, limit, offset, mocker, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?per_page={quote(limit)}&page={quote(page)}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": limit,
            "offset": offset,
            "filter": mocker.ANY,
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize("page,per_page", ((0, 10), (-1, 10), (1, 0), (1, -5), (1, 101), (21474838, 100)))
def test_response_invalid_pagination(page, per_page, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=f"?per_page={quote(per_page)}&page={quote(page)}")
    response_status, response_data = api_get(url)

    assert response_status == 400

    graphql_query_empty_response.assert_not_called()


def test_query_variables_default_except_staleness(mocker, graphql_query_empty_response, api_get):
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": "modified_on",
            "order_how": "DESC",
            "limit": 50,
            "offset": 0,
            "filter": mocker.ANY,
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_variables_default_staleness(mocker, culling_datetime_mock, graphql_query_empty_response, api_get):
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    assert_graph_query_single_call_with_staleness(
        mocker,
        graphql_query_empty_response,
        (
            {"gt": "2019-12-16T10:10:06.754201+00:00"},  # fresh
            {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"},  # stale
            {"eq": None},  # unknown
        ),
    )


@pytest.mark.parametrize(
    "staleness,expected",
    (
        ("fresh", {"gt": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale", {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale_warning", {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
        ("unknown", {"eq": None}),
    ),
)
def test_query_variables_staleness(
    staleness, expected, mocker, culling_datetime_mock, graphql_query_empty_response, api_get
):
    url = build_hosts_url(query=f"?staleness={staleness}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    assert_graph_query_single_call_with_staleness(mocker, graphql_query_empty_response, (expected,))


def test_query_multiple_staleness(mocker, culling_datetime_mock, graphql_query_empty_response, api_get):
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
    field, value, mocker, culling_datetime_mock, graphql_query_empty_response, api_get
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
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_response_processed_properly(graphql_query_with_response, api_get):
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
                "org_id": "test",
                "display_name": "test01.rhel7.jharting.local",
                "ansible_host": "test01.rhel7.jharting.local",
                "created": "2019-02-10T08:07:03.354307+00:00",
                "updated": "2019-02-10T08:07:03.354312+00:00",
                "fqdn": "fqdn.test01.rhel7.jharting.local",
                "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                "reporter": "puptoo",
                "per_reporter_staleness": {
                    "puptoo": {
                        "check_in_succeeded": True,
                        "last_check_in": "2020-02-10T08:07:03.354307+00:00",
                        "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                    }
                },
                "subscription_manager_id": None,
                "bios_uuid": None,
                "ip_addresses": None,
                "mac_addresses": None,
                "provider_id": None,
                "provider_type": None,
                "stale_warning_timestamp": "2020-02-17T08:07:03.354307+00:00",
                "culled_timestamp": "2020-02-24T08:07:03.354307+00:00",
                "facts": [],
            },
            {
                "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                "account": "test",
                "org_id": "test",
                "display_name": "test02.rhel7.jharting.local",
                "ansible_host": "test02.rhel7.jharting.local",
                "created": "2019-01-10T08:07:03.354307+00:00",
                "updated": "2019-01-10T08:07:03.354312+00:00",
                "fqdn": "fqdn.test02.rhel7.jharting.local",
                "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                "stale_timestamp": "2020-01-10T08:07:03.354307+00:00",
                "reporter": "yupana",
                "per_reporter_staleness": {
                    "yupana": {
                        "check_in_succeeded": True,
                        "last_check_in": "2020-02-10T08:07:03.354307+00:00",
                        "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                    }
                },
                "subscription_manager_id": None,
                "bios_uuid": None,
                "ip_addresses": None,
                "mac_addresses": None,
                "provider_id": None,
                "provider_type": None,
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


def test_response_pagination_index_error(graphql_query_with_response, api_get):
    url = build_hosts_url(query="?per_page=2&page=3")
    response_status, response_data = api_get(url)

    assert response_status == 404

    graphql_query_with_response.assert_called_once()


def test_valid_without_decimal_part(graphql_query, api_get):
    response = xjoin_host_response("2020-02-10T08:07:03Z")

    graphql_query(return_value=response)
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200
    assert response_data["results"][0]["stale_timestamp"] == "2020-02-10T08:07:03+00:00"


def test_valid_with_offset_timezone(graphql_query, api_get):
    response = xjoin_host_response("2020-02-10T08:07:03.354307+01:00")

    graphql_query(return_value=response)
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200
    assert response_data["results"][0]["stale_timestamp"] == "2020-02-10T07:07:03.354307+00:00"


def test_invalid_without_timezone(graphql_query, api_get):
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


def test_tags_query_variables_default_except_staleness(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(TAGS_URL, {"OR": mocker.ANY})


# Test basic query filters
@pytest.mark.parametrize(
    "field,matcher,value",
    (
        ("fqdn", "eq", "some fqdn"),
        ("fqdn", "eq", "some Capitalized FQDN"),
        ("display_name", "matches_lc", "*some display name*"),
        ("insights_id", "eq", generate_uuid()),
        ("insights_id", "eq", generate_uuid().upper()),
        ("provider_id", "eq", "some-provider-id"),
        ("provider_id", "eq", "ANOTHER-provider-id"),
        ("provider_type", "eq", ProviderType.AZURE.value),
    ),
)
def test_tags_query_host_filters(assert_tag_query_host_filter_for_field, field, matcher, value):
    assert_tag_query_host_filter_for_field(
        build_tags_url(query=f"?{field}={quote(value.replace('*',''))}"), field, matcher, value
    )


# Test query filters for only casefolded fields
@pytest.mark.parametrize(
    "field,matcher,value",
    (
        ("fqdn", "eq", "some Capitalized FQDN"),
        ("insights_id", "eq", generate_uuid().upper()),
        ("provider_id", "eq", "CAPITALIZED-provider-id"),
    ),
)
def test_tags_query_host_filters_casefolding(assert_tag_query_host_filter_for_field, field, matcher, value):
    assert_tag_query_host_filter_for_field(
        build_tags_url(query=f"?{field}={quote(value.replace('*',''))}"), field, matcher, value
    )


def test_tags_query_variables_default_staleness(
    mocker, culling_datetime_mock, graphql_tag_query_empty_response, api_get
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
                    {"stale_timestamp": {"eq": None}},
                ]
            },
        },
        mocker.ANY,
    )


@pytest.mark.parametrize(
    "staleness,expected",
    (
        ("fresh", {"gt": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale", {"gt": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
        ("stale_warning", {"gt": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
        ("unknown", {"eq": None}),
    ),
)
def test_tags_query_variables_staleness(
    staleness, expected, culling_datetime_mock, assert_tag_query_host_filter_single_call
):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query=f"?staleness={staleness}"), host_filter={"OR": [{"stale_timestamp": expected}]}
    )


def test_tags_multiple_query_variables_staleness(culling_datetime_mock, assert_tag_query_host_filter_single_call):
    staleness = "fresh,stale_warning"
    assert_tag_query_host_filter_single_call(
        build_tags_url(query=f"?staleness={staleness}"),
        host_filter={
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
    )


def test_query_variables_tags_simple(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?tags=insights-client/os=fedora"),
        host_filter={
            "OR": mocker.ANY,
            "AND": (
                {"tag": {"namespace": {"eq": "insights-client"}, "key": {"eq": "os"}, "value": {"eq": "fedora"}}},
            ),
        },
    )


def test_query_variables_tags_with_special_characters_unescaped(mocker, assert_tag_query_host_filter_single_call):
    tags_query = quote(";?:@&+$/-_.!~*'()=#")
    assert_tag_query_host_filter_single_call(
        build_tags_url(query=f"?tags={tags_query}"),
        host_filter={
            "AND": ({"tag": {"namespace": {"eq": ";?:@&+$"}, "key": {"eq": "-_.!~*'()"}, "value": {"eq": "#"}}},),
            "OR": mocker.ANY,
        },
    )


def test_query_variables_tags_with_special_characters_escaped(mocker, assert_tag_query_host_filter_single_call):
    namespace = quote_everything(";,/?:@&=+$")
    key = quote_everything("-_.!~*'()")
    value = quote_everything("#")
    tags_query = quote(f"{namespace}/{key}={value}")

    assert_tag_query_host_filter_single_call(
        build_tags_url(query=f"?tags={tags_query}"),
        host_filter={
            "AND": ({"tag": {"namespace": {"eq": ";,/?:@&=+$"}, "key": {"eq": "-_.!~*'()"}, "value": {"eq": "#"}}},),
            "OR": mocker.ANY,
        },
    )


def test_query_variables_tags_collection_multi(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?tags=Sat/env=prod&tags=insights-client/os=fedora"),
        host_filter={
            "AND": (
                {"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},
                {"tag": {"namespace": {"eq": "insights-client"}, "key": {"eq": "os"}, "value": {"eq": "fedora"}}},
            ),
            "OR": mocker.ANY,
        },
    )


def test_query_variables_tags_collection_encoded_commas(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?tags=Sat/env=prod%2Cstage&tags=insights-client/os=fedora%2Cubuntu"),
        host_filter={
            "AND": (
                {"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": "prod,stage"}}},
                {
                    "tag": {
                        "namespace": {"eq": "insights-client"},
                        "key": {"eq": "os"},
                        "value": {"eq": "fedora,ubuntu"},
                    }
                },
            ),
            "OR": mocker.ANY,
        },
    )


def test_query_variables_tags_without_namespace(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?tags=env=prod"),
        host_filter={
            "AND": ({"tag": {"namespace": {"eq": None}, "key": {"eq": "env"}, "value": {"eq": "prod"}}},),
            "OR": mocker.ANY,
        },
    )


def test_query_variables_tags_without_value(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?tags=Sat/env"),
        host_filter={
            "AND": ({"tag": {"namespace": {"eq": "Sat"}, "key": {"eq": "env"}, "value": {"eq": None}}},),
            "OR": mocker.ANY,
        },
    )


def test_query_variables_tags_with_only_key(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?tags=env"),
        host_filter={
            "AND": ({"tag": {"namespace": {"eq": None}, "key": {"eq": "env"}, "value": {"eq": None}}},),
            "OR": mocker.ANY,
        },
    )


def test_tags_query_variables_search(mocker, assert_tag_query_host_filter_single_call):
    query = "Δwithčhar!/~|+ "
    assert_tag_query_host_filter_single_call(
        build_tags_url(query=f"?search={quote(query)}"),
        host_filter={"OR": mocker.ANY},
        filter={"search": {"regex": f".*{custom_escape(query)}.*"}},
    )


@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_tags_query_variables_ordering_dir(direction, mocker, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query=f"?order_how={direction}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": "tag", "order_how": direction, "limit": 50, "offset": 0, "hostFilter": {"OR": mocker.ANY}},
        mocker.ANY,
    )


@pytest.mark.parametrize("ordering", ["tag", "count"])
def test_tags_query_variables_ordering_by(ordering, mocker, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query=f"?order_by={ordering}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": ordering, "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": mocker.ANY}},
        mocker.ANY,
    )


@pytest.mark.parametrize("page,limit,offset", [(1, 2, 0), (2, 2, 2), (4, 50, 150)])
def test_tags_response_pagination(page, limit, offset, mocker, graphql_tag_query_empty_response, api_get):
    url = build_tags_url(query=f"?per_page={limit}&page={page}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": "tag", "order_how": "ASC", "limit": limit, "offset": offset, "hostFilter": {"OR": mocker.ANY}},
        mocker.ANY,
    )


@pytest.mark.parametrize("page,per_page", [(0, 10), (-1, 10), (1, 0), (1, -5), (1, 101), (21474838, 100)])
def test_tags_response_invalid_pagination(page, per_page, api_get):
    url = build_tags_url(query=f"?per_page={per_page}&page={page}")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_tags_query_variables_registered_with(mocker, assert_tag_query_host_filter_single_call):
    assert_tag_query_host_filter_single_call(
        build_tags_url(query="?registered_with=insights"),
        host_filter={
            "OR": mocker.ANY,
            "AND": ({"OR": [{"NOT": {"insights_id": {"eq": None}}}]},),
        },
    )


@pytest.mark.parametrize(
    "reporters",
    (
        ["cloud-connector"],
        ["puptoo", "yupana"],
        ["cloud-connector", "puptoo", "rhsm-conduit"],
        ["!puptoo"],
        ["!yupana", "puptoo"],
        ["!yupana", "!puptoo", "rhsm-conduit"],
    ),
)
def test_tags_query_variables_registered_with_per_reporter(
    mocker, assert_tag_query_host_filter_single_call, reporters
):

    tags_url = build_tags_url(query="?" + "&".join([f"registered_with={reporter}" for reporter in reporters]))

    prs_array = _build_prs_array(mocker, reporters)

    assert_tag_query_host_filter_single_call(
        tags_url,
        host_filter={
            "OR": mocker.ANY,
            "AND": ({"OR": prs_array},),
        },
    )


def test_tags_response_invalid_registered_with(api_get):
    url = build_tags_url(query="?registered_with=salad")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_tags_response_processed_properly(graphql_tag_query_with_response, api_get):
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


def test_tags_response_pagination_index_error(mocker, graphql_tag_query_with_response, api_get):
    url = build_tags_url(query="?per_page=2&page=3")
    response_status, response_data = api_get(url)

    assert response_status == 404

    graphql_tag_query_with_response.assert_called_once_with(
        TAGS_QUERY,
        {"order_by": "tag", "order_how": "ASC", "limit": 2, "offset": 4, "hostFilter": {"OR": mocker.ANY}},
        mocker.ANY,
    )


def test_tags_RBAC_allowed(
    subtests, mocker, graphql_tag_query_empty_response, enable_rbac, assert_tag_query_host_filter_single_call
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            assert_tag_query_host_filter_single_call(
                build_tags_url(query="?registered_with=insights"),
                host_filter={
                    "OR": mocker.ANY,
                    "AND": ({"OR": [{"NOT": {"insights_id": {"eq": None}}}]},),
                },
            )
            graphql_tag_query_empty_response.reset_mock()


def test_tags_RBAC_denied(subtests, mocker, graphql_tag_query_empty_response, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_url(query="?registered_with=insights")
            response_status, response_data = api_get(url)

            assert response_status == 403

            graphql_tag_query_empty_response.assert_not_called()


def test_system_profile_sap_system_endpoint(mocker, graphql_system_profile_sap_system_query_empty_response, api_get):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY}, "limit": 50, "offset": 0}, mocker.ANY
    )


@pytest.mark.parametrize(
    "tags,query_param",
    (
        (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},), f"?tags={quote('a/b=c')}"),
        (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": None}},), f"?tags={quote('a/b')}"),
        (
            (
                {"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},
                {"namespace": {"eq": "d"}, "key": {"eq": "e"}, "value": {"eq": "f"}},
            ),
            f"?tags={quote('a/b=c')}&tags={quote('d/e=f')}",
        ),
        (
            ({"namespace": {"eq": "a/a=a"}, "key": {"eq": "b/b=b"}, "value": {"eq": "c/c=c"}},),
            "?tags=" + quote(quote("a/a=a") + "/" + quote("b/b=b") + "=" + quote("c/c=c")),
        ),
        (({"namespace": {"eq": "ɑ"}, "key": {"eq": "β"}, "value": {"eq": "ɣ"}},), f"?tags={quote('ɑ/β=ɣ')}"),
    ),
)
def test_system_profile_sap_system_endpoint_tags(
    tags, query_param, mocker, graphql_system_profile_sap_system_query_empty_response, api_get
):
    url = build_system_profile_sap_system_url(query=query_param)

    response_status, response_data = api_get(url)

    tag_filters = tuple({"tag": item} for item in tags)
    assert response_status == 200
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY, "AND": tag_filters}, "limit": 50, "offset": 0}, mocker.ANY
    )


@pytest.mark.parametrize(
    "reporters",
    (
        ["cloud-connector"],
        ["puptoo", "yupana"],
        ["cloud-connector", "puptoo", "rhsm-conduit"],
        ["!puptoo"],
        ["!yupana", "puptoo"],
        ["!yupana", "!puptoo", "rhsm-conduit"],
    ),
)
def test_system_profile_sap_system_endpoint_registered_with_per_reporter(
    mocker, graphql_system_profile_sap_system_query_empty_response, api_get, reporters
):
    url = build_system_profile_sap_system_url(
        query="?" + "&".join([f"registered_with={reporter}" for reporter in reporters])
    )

    response_status, response_data = api_get(url)

    assert response_status == 200

    prs_array = _build_prs_array(mocker, reporters)

    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY,
        {
            "hostFilter": {"OR": mocker.ANY, "AND": ({"OR": prs_array},)},
            "limit": 50,
            "offset": 0,
        },
        mocker.ANY,
    )


def test_system_profile_sap_system_endpoint_pagination(
    mocker, graphql_system_profile_sap_system_query_empty_response, api_get
):
    page, per_page = 1, 20
    url = build_system_profile_sap_system_url(query=f"?page={page}&per_page={per_page}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY, {"hostFilter": {"OR": mocker.ANY}, "limit": per_page, "offset": page - 1}, mocker.ANY
    )


def test_system_profile_sap_sids_endpoint_pagination(
    mocker, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    page, per_page = 1, 85
    url = build_system_profile_sap_sids_url(query=f"?page={page}&per_page={per_page}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY}, "limit": per_page, "offset": page - 1}, mocker.ANY
    )


def test_system_profile_sap_sids_endpoint(mocker, graphql_system_profile_sap_sids_query_empty_response, api_get):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY}, "limit": 50, "offset": 0}, mocker.ANY
    )


@pytest.mark.parametrize(
    "tags,query_param",
    (
        (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},), f"?tags={quote('a/b=c')}"),
        (({"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": None}},), f"?tags={quote('a/b')}"),
        (
            (
                {"namespace": {"eq": "a"}, "key": {"eq": "b"}, "value": {"eq": "c"}},
                {"namespace": {"eq": "d"}, "key": {"eq": "e"}, "value": {"eq": "f"}},
            ),
            f"?tags={quote('a/b=c')}&tags={quote('d/e=f')}",
        ),
        (
            ({"namespace": {"eq": "a/a=a"}, "key": {"eq": "b/b=b"}, "value": {"eq": "c/c=c"}},),
            "?tags=" + quote(quote("a/a=a") + "/" + quote("b/b=b") + "=" + quote("c/c=c")),
        ),
        (({"namespace": {"eq": "ɑ"}, "key": {"eq": "β"}, "value": {"eq": "ɣ"}},), f"?tags={quote('ɑ/β=ɣ')}"),
    ),
)
def test_system_profile_sap_sids_endpoint_tags(
    tags, query_param, mocker, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    url = build_system_profile_sap_sids_url(query=query_param)

    response_status, response_data = api_get(url)

    tag_filters = tuple({"tag": item} for item in tags)
    assert response_status == 200
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY, {"hostFilter": {"OR": mocker.ANY, "AND": tag_filters}, "limit": 50, "offset": 0}, mocker.ANY
    )


@pytest.mark.parametrize(
    "reporters",
    (
        ["cloud-connector"],
        ["puptoo", "yupana"],
        ["cloud-connector", "puptoo", "rhsm-conduit", "yupana"],
        ["!puptoo"],
        ["!yupana", "puptoo"],
        ["!yupana", "!puptoo", "rhsm-conduit"],
    ),
)
def test_system_profile_sap_sids_endpoint_registered_with_per_reporter(
    mocker, graphql_system_profile_sap_sids_query_empty_response, api_get, reporters
):
    url = build_system_profile_sap_sids_url(
        query="?" + "&".join([f"registered_with={reporter}" for reporter in reporters])
    )

    response_status, response_data = api_get(url)

    assert response_status == 200

    prs_array = _build_prs_array(mocker, reporters)

    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY,
        {
            "hostFilter": {
                "OR": mocker.ANY,
                "AND": ({"OR": prs_array},),
            },
            "limit": 50,
            "offset": 0,
        },
        mocker.ANY,
    )


def test_query_hosts_filter_spf_sap_system(mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get):
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


def test_query_tags_filter_spf_sap_system(
    mocker, subtests, graphql_tag_query_empty_response, assert_tag_query_host_filter_single_call
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
                assert_tag_query_host_filter_single_call(
                    build_tags_url(query=f"?filter{path}={value}"), host_filter={"OR": mocker.ANY, "AND": query}
                )
                graphql_tag_query_empty_response.reset_mock()


def test_query_system_profile_sap_system_filter_spf_sap_sids(
    mocker, subtests, graphql_system_profile_sap_system_query_empty_response, api_get
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
                    SAP_SYSTEM_QUERY,
                    {"hostFilter": {"OR": mocker.ANY, "AND": query}, "limit": 50, "offset": 0},
                    mocker.ANY,
                )


def test_query_hosts_filter_spf_sap_sids(mocker, subtests, graphql_query_empty_response, api_get):
    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("XQC",), ("ABC", "A12"), ("M80", "BEN"))
    queries = (
        ({"AND": [{"spf_sap_sids": {"eq": "XQC"}}]},),
        ({"AND": [{"spf_sap_sids": {"eq": "ABC"}}, {"spf_sap_sids": {"eq": "A12"}}]},),
        ({"AND": [{"spf_sap_sids": {"eq": "M80"}}, {"spf_sap_sids": {"eq": "BEN"}}]},),
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )


def test_query_tags_filter_spf_sap_sids(
    mocker, subtests, graphql_tag_query_empty_response, assert_tag_query_host_filter_single_call
):
    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("XQC",), ("ABC", "A12"), ("M80", "BEN"))
    queries = (
        ({"AND": [{"spf_sap_sids": {"eq": "XQC"}}]},),
        ({"AND": [{"spf_sap_sids": {"eq": "ABC"}}, {"spf_sap_sids": {"eq": "A12"}}]},),
        ({"AND": [{"spf_sap_sids": {"eq": "M80"}}, {"spf_sap_sids": {"eq": "BEN"}}]},),
    )

    for path in filter_paths:
        for values, query in zip(value_sets, queries):
            with subtests.test(values=values, query=query, path=path):
                assert_tag_query_host_filter_single_call(
                    build_tags_url(query="?" + "".join([f"filter{path}={value}&" for value in values])),
                    host_filter={"OR": mocker.ANY, "AND": query},
                )
                graphql_tag_query_empty_response.reset_mock()


def test_query_system_profile_sap_sids_filter_spf_sap_sids(
    mocker, subtests, graphql_system_profile_sap_sids_query_empty_response, api_get
):
    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("XQC",), ("ABC", "A12"), ("M80", "BEN"))
    queries = (
        ({"AND": [{"spf_sap_sids": {"eq": "XQC"}}]},),
        ({"AND": [{"spf_sap_sids": {"eq": "ABC"}}, {"spf_sap_sids": {"eq": "A12"}}]},),
        ({"AND": [{"spf_sap_sids": {"eq": "M80"}}, {"spf_sap_sids": {"eq": "BEN"}}]},),
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
                    SAP_SIDS_QUERY,
                    {"hostFilter": {"OR": mocker.ANY, "AND": query}, "limit": 50, "offset": 0},
                    mocker.ANY,
                )


def test_query_system_profile_sap_sids_with_search(
    mocker, subtests, graphql_system_profile_sap_sids_query_with_response, api_get
):
    url = build_system_profile_sap_sids_url(query="?search=C2")

    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_system_profile_sap_sids_query_with_response.assert_called_once_with(
        SAP_SIDS_QUERY,
        {"hostFilter": {"OR": mocker.ANY}, "filter": {"search": {"regex": ".*C2.*"}}, "limit": 50, "offset": 0},
        mocker.ANY,
    )


# system_profile is_marketplace tests
def test_query_hosts_filter_spf_is_marketplace(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][is_marketplace]", "[system_profile][is_marketplace][eq]")
    values = ("true", "false", "nil", "not_nil")
    queries = (
        {"spf_is_marketplace": {"is": True}},
        {"spf_is_marketplace": {"is": False}},
        {"spf_is_marketplace": {"is": None}},
        {"NOT": {"spf_is_marketplace": {"is": None}}},
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


# system_profile rhc_client_id tests
def test_query_hosts_filter_spf_rhc_client_id(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][rhc_client_id]", "[system_profile][rhc_client_id][eq]")
    values = ("8dd97934-8ce4-11eb-8dcd-0242ac130003", "nil", "not_nil")
    queries = (
        {"spf_rhc_client_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_rhc_client_id": {"eq": None}},
        {"NOT": {"spf_rhc_client_id": {"eq": None}}},
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


def test_query_hosts_filter_spf_rhc_client_id_multiple(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    query_params = (
        "?filter[system_profile][rhc_client_id][eq][]=8dd97934-8ce4-11eb-8dcd-0242ac130003",
        "?filter[system_profile][rhc_client_id][eq][]=8dd97934-8ce4-11eb-8dcd-0242ac130003"
        "&filter[system_profile][rhc_client_id][eq][]=6e2c3332-936c-4167-b9be-c219f4303c85",
    )
    queries = (
        {"OR": [{"spf_rhc_client_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}}]},
        {
            "OR": [
                {"spf_rhc_client_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
                {"spf_rhc_client_id": {"eq": "6e2c3332-936c-4167-b9be-c219f4303c85"}},
            ]
        },
    )

    for param, query in zip(query_params, queries):
        with subtests.test(param=param, query=query):
            url = build_hosts_url(query=param)

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
                    "fields": mocker.ANY,
                },
                mocker.ANY,
            )
            graphql_query_empty_response.reset_mock()


@pytest.mark.parametrize(
    "field,value", (("insights_id", "a58c53e0-8000-4384-b902-c70b69faacc5"), ("fqdn", "test.server.redhat.com"))
)
def test_xjoin_search_query_using_hostfilter(
    mocker, field, value, graphql_query_empty_response, patch_xjoin_post, api_delete_filtered_hosts
):
    response = {"data": XJOIN_HOSTS_RESPONSE_FOR_FILTERING}

    # Make the new hosts available in xjoin-search to make them available
    # for querying for deletion using filters
    patch_xjoin_post(response, status=200)

    api_delete_filtered_hosts({field: value})

    graphql_query_empty_response.assert_called_once_with(
        HOST_IDS_QUERY, {"filter": ({field: {"eq": value}},), "limit": mocker.ANY, "offset": 0}, mocker.ANY
    )


def test_xjoin_search_query_using_hostfilter_display_name(
    mocker, graphql_query_empty_response, api_delete_filtered_hosts
):
    query_params = {"display_name": "my awesome host uwu"}

    api_delete_filtered_hosts(query_params)

    graphql_query_empty_response.assert_called_once_with(
        HOST_IDS_QUERY,
        {
            "filter": ({"display_name": {"matches_lc": f"*{query_params['display_name']}*"}},),
            "limit": mocker.ANY,
            "offset": 0,
        },
        mocker.ANY,
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
            ["a/b=c", "d/e=f"],
        ),
        (
            ({"namespace": {"eq": "a/a=a"}, "key": {"eq": "b/b=b"}, "value": {"eq": "c/c=c"}},),
            quote("a/a=a") + "/" + quote("b/b=b") + "=" + quote("c/c=c"),
        ),
        (({"namespace": {"eq": "ɑ"}, "key": {"eq": "β"}, "value": {"eq": "ɣ"}},), "ɑ/β=ɣ"),
    ),
)
def test_xjoin_search_using_hostfilters_tags(
    tags, query_param, mocker, graphql_query_empty_response, api_delete_filtered_hosts
):
    query_params = {"tags": query_param}
    api_delete_filtered_hosts(query_params)

    tag_filters = tuple({"tag": item} for item in tags)

    graphql_query_empty_response.assert_called_once_with(
        HOST_IDS_QUERY, {"filter": tag_filters, "limit": mocker.ANY, "offset": 0}, mocker.ANY
    )


@pytest.mark.parametrize(
    "provider",
    (
        {"type": "alibaba", "id": generate_uuid()},
        {"type": "aws", "id": "i-05d2313e6b9a42b16"},
        {"type": "azure", "id": generate_uuid()},
        {"type": "gcp", "id": generate_uuid()},
        {"type": "ibm", "id": generate_uuid()},
    ),
)
def test_xjoin_search_query_using_hostfilter_provider(
    mocker, graphql_query_empty_response, provider, api_delete_filtered_hosts
):
    query_params = {"provider_type": provider["type"], "provider_id": provider["id"]}
    api_delete_filtered_hosts(query_params)

    graphql_query_empty_response.assert_called_once_with(
        HOST_IDS_QUERY,
        {
            "filter": ({"provider_type": {"eq": provider["type"]}}, {"provider_id": {"eq": provider["id"]}}),
            "limit": mocker.ANY,
            "offset": 0,
        },
        mocker.ANY,
    )


def test_spf_rhc_client_invalid_field_value(subtests, graphql_query_empty_response, patch_xjoin_post, api_get):
    query_params = (
        "?filter[system_profile][rhc_client_id][foo]=basicid",
        "?filter[system_profile][rhc_client_id][bar][]=basicid",
        "?filter[system_profile][rhc_client_id][eq][foo]=basicid",
        "?filter[system_profile][rhc_client_id][foo][]=basicid&filter[system_profile][rhc_client_id][bar][]=random",
    )
    for param in query_params:
        with subtests.test(param=param):
            url = build_hosts_url(query=param)
            response_status, response_data = api_get(url)
            assert response_status == 400
            assert response_data["title"] == "Validation Error"


# system_profile owner_id tests
def test_query_hosts_filter_spf_owner_id(mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get):
    filter_paths = ("[system_profile][owner_id]", "[system_profile][owner_id][eq]")
    values = ("8dd97934-8ce4-11eb-8dcd-0242ac130003", "nil", "not_nil")
    queries = (
        {"spf_owner_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_owner_id": {"eq": None}},
        {"NOT": {"spf_owner_id": {"eq": None}}},
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


def test_query_hosts_filter_spf_owner_id_multiple(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    query_params = (
        "?filter[system_profile][owner_id][eq][]=8dd97934-8ce4-11eb-8dcd-0242ac130003",
        "?filter[system_profile][owner_id][eq][]=8dd97934-8ce4-11eb-8dcd-0242ac130003"
        "&filter[system_profile][owner_id][eq][]=6e2c3332-936c-4167-b9be-c219f4303c85",
    )
    queries = (
        {"OR": [{"spf_owner_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}}]},
        {
            "OR": [
                {"spf_owner_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
                {"spf_owner_id": {"eq": "6e2c3332-936c-4167-b9be-c219f4303c85"}},
            ]
        },
    )

    for param, query in zip(query_params, queries):
        with subtests.test(param=param, query=query):
            url = build_hosts_url(query=param)

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
                    "fields": mocker.ANY,
                },
                mocker.ANY,
            )
            graphql_query_empty_response.reset_mock()


def test_spf_owner_id_invalid_field_value(subtests, graphql_query_empty_response, patch_xjoin_post, api_get):
    query_params = (
        "?filter[system_profile][owner_id][foo]=issasecret",
        "?filter[system_profile][owner_id][bar][]=issasecret",
        "?filter[system_profile][owner_id][eq][foo]=issasecret",
        "?filter[system_profile][owner_id][foo][]=issasecret&filter[system_profile][owner_id][bar][]=nothersecrect",
    )
    for param in query_params:
        with subtests.test(param=param):
            url = build_hosts_url(query=param)
            response_status, response_data = api_get(url)
            assert response_status == 400
            assert response_data["title"] == "Validation Error"


# system_profile host_type tests
def test_query_hosts_filter_spf_host_type(mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get):
    filter_paths = ("[system_profile][host_type]", "[system_profile][host_type][eq]")
    values = ("edge", "nil", "not_nil")
    queries = (
        {"spf_host_type": {"eq": "edge"}},
        {"spf_host_type": {"eq": None}},
        {"NOT": {"spf_host_type": {"eq": None}}},
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


def test_query_hosts_filter_spf_host_type_multiple(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    query_params = (
        "?filter[system_profile][host_type][eq][]=random-type",
        "?filter[system_profile][host_type][eq][]=edge" "&filter[system_profile][host_type][eq][]=random-type",
    )
    queries = (
        {"OR": [{"spf_host_type": {"eq": "random-type"}}]},
        {"OR": [{"spf_host_type": {"eq": "edge"}}, {"spf_host_type": {"eq": "random-type"}}]},
    )

    for param, query in zip(query_params, queries):
        with subtests.test(param=param, query=query):
            url = build_hosts_url(query=param)

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
                    "fields": mocker.ANY,
                },
                mocker.ANY,
            )
            graphql_query_empty_response.reset_mock()


def test_spf_host_type_invalid_field_value(subtests, graphql_query_empty_response, patch_xjoin_post, api_get):
    query_params = (
        "?filter[system_profile][host_type][foo]=what",
        "?filter[system_profile][host_type][bar][]=barbar",
        "?filter[system_profile][host_type][eq][foo]=foofoo",
        "?filter[system_profile][host_type][foo][]=foofoo&filter[system_profile][host_type][bar][]=barbar",
    )
    for param in query_params:
        with subtests.test(param=param):
            url = build_hosts_url(query=param)
            response_status, response_data = api_get(url)
            assert response_status == 400
            assert response_data["title"] == "Validation Error"


# system_profile insights_client_version tests
def test_query_hosts_filter_spf_insights_client_version(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][insights_client_version]", "[system_profile][insights_client_version][eq]")
    values = ("3.0.6-2.el7_6", "3.*", "nil", "not_nil")
    queries = (
        {"spf_insights_client_version": {"eq": "3.0.6-2.el7_6"}},
        {"spf_insights_client_version": {"matches": "3.*"}},
        {"spf_insights_client_version": {"eq": None}},
        {"NOT": {"spf_insights_client_version": {"eq": None}}},
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
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


# system_profile operating_system tests
def test_query_hosts_filter_spf_operating_system(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    http_queries = (
        "filter[system_profile][operating_system][RHEL][version][gte]=7.1",
        "filter[system_profile][operating_system][RHEL][version][gt]=7&"
        "filter[system_profile][operating_system][RHEL][version][lt]=9.2",
        "filter[system_profile][operating_system][RHEL][version][eq]=12.6&"
        "filter[system_profile][operating_system][CENT][version][gte]=7.1",
        "filter[system_profile][operating_system][RHEL][version][eq][]=8.0&"
        "filter[system_profile][operating_system][RHEL][version][eq][]=9.0",
    )

    graphql_queries = (
        {
            "OR": [
                {
                    "AND": [
                        {
                            "OR": [
                                {
                                    "spf_operating_system": {
                                        "major": {"eq": 7},
                                        "minor": {"gte": 1},
                                        "name": {"eq": "RHEL"},
                                    }
                                },
                                {"spf_operating_system": {"major": {"gt": 7}, "name": {"eq": "RHEL"}}},
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "OR": [
                {
                    "AND": [
                        {
                            "OR": [
                                {
                                    "spf_operating_system": {
                                        "major": {"eq": 9},
                                        "minor": {"lt": 2},
                                        "name": {"eq": "RHEL"},
                                    }
                                },
                                {"spf_operating_system": {"major": {"lt": 9}, "name": {"eq": "RHEL"}}},
                            ]
                        },
                        {"spf_operating_system": {"major": {"gt": 7}, "name": {"eq": "RHEL"}}},
                    ]
                }
            ]
        },
        {
            "OR": [
                {
                    "AND": [
                        {
                            "OR": [
                                {
                                    "spf_operating_system": {
                                        "major": {"eq": 7},
                                        "minor": {"gte": 1},
                                        "name": {"eq": "CENT"},
                                    }
                                },
                                {"spf_operating_system": {"major": {"gt": 7}, "name": {"eq": "CENT"}}},
                            ]
                        }
                    ]
                },
                {"AND": [{"spf_operating_system": {"major": {"eq": 12}, "minor": {"eq": 6}, "name": {"eq": "RHEL"}}}]},
            ]
        },
        {
            "OR": [
                {
                    "AND": [
                        {
                            "OR": [
                                {
                                    "spf_operating_system": {
                                        "major": {"eq": 8},
                                        "minor": {"eq": 0},
                                        "name": {"eq": "RHEL"},
                                    }
                                },
                                {
                                    "spf_operating_system": {
                                        "major": {"eq": 9},
                                        "minor": {"eq": 0},
                                        "name": {"eq": "RHEL"},
                                    }
                                },
                            ]
                        }
                    ]
                }
            ]
        },
    )

    for http_query, graphql_query in zip(http_queries, graphql_queries):
        with subtests.test(http_query=http_query, graphql_query=graphql_query):
            url = build_hosts_url(query=f"?{http_query}")

            response_status = api_get(url)[0]

            assert response_status == 200

            graphql_query_empty_response.assert_called_once_with(
                HOST_QUERY,
                {
                    "order_by": mocker.ANY,
                    "order_how": mocker.ANY,
                    "limit": mocker.ANY,
                    "offset": mocker.ANY,
                    "filter": ({"OR": mocker.ANY}, graphql_query),
                    "fields": mocker.ANY,
                },
                mocker.ANY,
            )
            graphql_query_empty_response.reset_mock()


# system_profile operating_system tests
def test_query_hosts_filter_spf_operating_system_exception_handling(
    mocker, subtests, graphql_query_empty_response, patch_xjoin_post, api_get
):
    http_queries = (
        "filter[system_profile][operating_system][RHEL][version][fake_op]=7.1",
        "filter[system_profile][operating_system][RHEL]=7.1",
        "filter[system_profile][operating_system][CENT]=",
        "filter[system_profile][operating_system][CENT]=something",
        "filter[system_profile][operating_system][RHEL][version][eq][]=9.0.1",
    )

    for http_query in http_queries:
        with subtests.test(http_query=http_query):
            url = build_hosts_url(query=f"?{http_query}")

            response_status, response_data = api_get(url)

            assert response_status == 400
            assert response_data["title"] == "Validation Error"


# system_profile ansible filtering tests
def test_query_hosts_filter_spf_ansible(mocker, subtests, graphql_query_empty_response, api_get):
    http_queries = (
        "filter[system_profile][ansible][controller_version]=7.1",
        "filter[system_profile][ansible][hub_version]=8.0.*",
        "filter[system_profile][ansible][catalog_worker_version]=nil",
        "filter[system_profile][ansible][sso_version]=0.44.963",
        "filter[system_profile][ansible][controller_version]=7.1&filter[system_profile][ansible][hub_version]=not_nil",
        "filter[system_profile][ansible][catalog_worker_version][]=8.0"
        "&filter[system_profile][ansible][catalog_worker_version][]=9.0",
        "filter[system_profile][ansible][hub_version]=not_nil&filter[system_profile][ansible][catalog_worker_version]"
        "[]=8.0&filter[system_profile][ansible][catalog_worker_version][]=9.0",
    )

    graphql_queries = (
        {"AND": [{"spf_ansible": {"controller_version": {"eq": "7.1"}}}]},
        {"AND": [{"spf_ansible": {"hub_version": {"matches": "8.0.*"}}}]},
        {"AND": [{"spf_ansible": {"catalog_worker_version": {"eq": None}}}]},
        {"AND": [{"spf_ansible": {"sso_version": {"eq": "0.44.963"}}}]},
        {
            "AND": [
                {"NOT": {"spf_ansible": {"hub_version": {"eq": None}}}},
                {"spf_ansible": {"controller_version": {"eq": "7.1"}}},
            ]
        },
        {
            "AND": [
                {
                    "OR": [
                        {"spf_ansible": {"catalog_worker_version": {"eq": "8.0"}}},
                        {"spf_ansible": {"catalog_worker_version": {"eq": "9.0"}}},
                    ]
                }
            ]
        },
        {
            "AND": [
                {
                    "OR": [
                        {"spf_ansible": {"catalog_worker_version": {"eq": "8.0"}}},
                        {"spf_ansible": {"catalog_worker_version": {"eq": "9.0"}}},
                    ]
                },
                {"NOT": {"spf_ansible": {"hub_version": {"eq": None}}}},
            ]
        },
    )

    for http_query, graphql_query in zip(http_queries, graphql_queries):
        with subtests.test(http_query=http_query, graphql_query=graphql_query):
            url = build_hosts_url(query=f"?{http_query}")

            response_status = api_get(url)[0]

            assert response_status == 200

            graphql_query_empty_response.assert_called_once_with(
                HOST_QUERY,
                {
                    "order_by": mocker.ANY,
                    "order_how": mocker.ANY,
                    "limit": mocker.ANY,
                    "offset": mocker.ANY,
                    "filter": ({"OR": mocker.ANY}, graphql_query),
                    "fields": mocker.ANY,
                },
                mocker.ANY,
            )
            graphql_query_empty_response.reset_mock()


# system_profile deep object filtering
def test_query_hosts_filter_deep_objects(mocker, subtests, flask_app, graphql_query_empty_response, api_get):
    http_queries = (
        "filter[system_profile][ansible][d0n1][d1n2][name]=foo",
        "filter[system_profile][ansible][d0n1][d1n1][d2n1][name]=bar",
        "filter[system_profile][ansible][d0n1][d1n1][d2n2][name]=nil",
    )

    graphql_queries = (
        {"AND": [{"spf_ansible": {"d0n1": {"d1n2": {"name": {"eq": "foo"}}}}}]},
        {"AND": [{"spf_ansible": {"d0n1": {"d1n1": {"d2n1": {"name": {"eq": "bar"}}}}}}]},
        {"AND": [{"spf_ansible": {"d0n1": {"d1n1": {"d2n2": {"name": {"eq": None}}}}}}]},
    )

    with flask_app.app_context():
        mocker.patch(
            "api.filtering.filtering.system_profile_spec",
            return_value=process_spec(system_profile_deep_object_spec()["$defs"]["SystemProfile"]["properties"])[0],
        )

        for http_query, graphql_query in zip(http_queries, graphql_queries):
            with subtests.test(http_query=http_query, graphql_query=graphql_query):
                url = build_hosts_url(query=f"?{http_query}")

                response_status = api_get(url)[0]

                assert response_status == 200

                graphql_query_empty_response.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": mocker.ANY,
                        "order_how": mocker.ANY,
                        "limit": mocker.ANY,
                        "offset": mocker.ANY,
                        "filter": ({"OR": mocker.ANY}, graphql_query),
                        "fields": mocker.ANY,
                    },
                    mocker.ANY,
                )
                graphql_query_empty_response.reset_mock()


# system_profile fields not in schema validation failstate tests
def test_query_hosts_filter_spf_not_in_schema_exception_handling(subtests, api_get):
    http_queries = (
        "filter[system_profile][i_love_ketchup]=yum",
        "filter[system_profile][fake_field][fake_sub_field]=3.14",
    )

    for http_query in http_queries:
        with subtests.test(http_query=http_query):
            url = build_hosts_url(query=f"?{http_query}")

            response_status, response_data = api_get(url)

            assert response_status == 400
            assert response_data["title"] == "Validation Error"


# system_profile ansible failstate tests
def test_query_hosts_filter_spf_ansible_exception_handling(subtests, api_get):
    http_queries = (
        "filter[system_profile][ansible][controller_version][fake_op]=7.1",
        "filter[system_profile][ansible]=7.1",
        "filter[system_profile][ansible]=something",
    )

    for http_query in http_queries:
        with subtests.test(http_query=http_query):
            url = build_hosts_url(query=f"?{http_query}")

            response_status, response_data = api_get(url)

            assert response_status == 400
            assert response_data["title"] == "Validation Error"


def test_query_hosts_system_identity(mocker, subtests, graphql_query_empty_response, api_get):
    url = build_hosts_url()

    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"OR": mocker.ANY}, {"spf_owner_id": {"eq": OWNER_ID}}),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def test_query_tags_system_identity(mocker, subtests, graphql_tag_query_empty_response, api_get):
    url = build_tags_url()

    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert response_status == 200

    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "hostFilter": {"OR": mocker.ANY, "AND": ({"spf_owner_id": {"eq": OWNER_ID}},)},
        },
        mocker.ANY,
    )


def test_query_system_profile_sap_sids_system_identity(
    mocker, subtests, graphql_system_profile_sap_sids_query_with_response, api_get
):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert response_status == 200

    graphql_system_profile_sap_sids_query_with_response.assert_called_once_with(
        SAP_SIDS_QUERY,
        {"hostFilter": {"OR": mocker.ANY, "AND": ({"spf_owner_id": {"eq": OWNER_ID}},)}, "limit": 50, "offset": 0},
        mocker.ANY,
    )


def test_query_system_profile_sap_system_system_identity(
    mocker, subtests, graphql_system_profile_sap_system_query_with_response, api_get
):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert response_status == 200

    graphql_system_profile_sap_system_query_with_response.assert_called_once_with(
        SAP_SYSTEM_QUERY,
        {"hostFilter": {"OR": mocker.ANY, "AND": ({"spf_owner_id": {"eq": OWNER_ID}},)}, "limit": 50, "offset": 0},
        mocker.ANY,
    )


def test_query_with_owner_id_satellite_identity(mocker, subtests, graphql_query_empty_response, api_get):
    url = build_hosts_url()

    response_status, response_data = api_get(url, SATELLITE_IDENTITY)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"OR": mocker.ANY}, {"spf_owner_id": {"eq": SATELLITE_IDENTITY["system"]["cn"]}}),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize(
    "variables,query",
    (
        (
            {
                "fields": ["arch", "operating_system", "os_release"],
                "limit": 50,
                "offset": 0,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=arch,operating_system,os_release",
        ),
        (
            {
                "fields": ["arch", "operating_system"],
                "limit": 2,
                "offset": 0,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=arch,operating_system&per_page=2",
        ),
        (
            {
                "fields": ["arch", "operating_system"],
                "limit": 1,
                "offset": 1,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=arch,operating_system&per_page=1&page=2",
        ),
        (
            {
                "fields": ["arch", "operating_system"],
                "limit": 50,
                "offset": 0,
                "order_by": "display_name",
                "order_how": "ASC",
            },
            "?fields[system_profile]=arch,operating_system&order_by=display_name&order_how=ASC",
        ),
        (
            {
                "fields": ["arch", "operating_system"],
                "limit": 1,
                "offset": 1,
                "order_by": "display_name",
                "order_how": "ASC",
            },
            "?fields[system_profile]=arch,operating_system&order_by=display_name&order_how=ASC&per_page=1&page=2",
        ),
        (
            {
                "fields": ["arch", "operating_system"],
                "limit": 1,
                "offset": 1,
                "order_by": "modified_on",
                "order_how": "DESC",
            },
            "?fields[system_profile]=arch,operating_system&order_by=updated&order_how=DESC&per_page=1&page=2",
        ),
        (
            {
                "fields": ["arch", "operating_system", "os_release", "last_boot_time"],
                "limit": 1,
                "offset": 1,
                "order_by": "display_name",
                "order_how": "ASC",
            },
            "?fields[system_profile]=arch,operating_system&order_by=display_name&order_how=ASC&per_page=1\
                &fields[system_profile]=os_release,last_boot_time&page=2",
        ),
        (
            {
                "fields": ["arch", "operating_system"],
                "limit": 50,
                "offset": 0,
                "order_by": "operating_system",
                "order_how": "DESC",
            },
            "?fields[system_profile]=arch,operating_system&order_by=operating_system&order_how=DESC"
            "&per_page=50&page=1",
        ),
    ),
)
def test_sp_sparse_xjoin_query_translation(
    variables, query, mocker, graphql_sparse_system_profile_empty_response, api_get
):
    host_one_id, host_two_id = generate_uuid(), generate_uuid()

    hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

    # Test with user identity first
    variables["hostFilter"] = [{"OR": [{"id": {"eq": host_one_id}}, {"id": {"eq": host_two_id}}]}]

    response_status, _ = api_get(build_system_profile_url(hosts, query=query))

    assert response_status == 200
    graphql_sparse_system_profile_empty_response.assert_called_once_with(
        SYSTEM_PROFILE_SPARSE_QUERY, variables, mocker.ANY
    )

    graphql_sparse_system_profile_empty_response.reset_mock()

    # Now test with system identity
    variables["hostFilter"] = [
        {"OR": [{"id": {"eq": host_one_id}}, {"id": {"eq": host_two_id}}]},
        {"spf_owner_id": {"eq": SYSTEM_IDENTITY["system"]["cn"]}},
    ]

    response_status, _ = api_get(build_system_profile_url(hosts, query=query), identity=SYSTEM_IDENTITY)

    assert response_status == 200
    graphql_sparse_system_profile_empty_response.assert_called_once_with(
        SYSTEM_PROFILE_SPARSE_QUERY, variables, mocker.ANY
    )


@pytest.mark.parametrize(
    "query,fields",
    (
        ("?fields[system_profile]=arch", ["arch"]),
        ("?fields[system_profile]=arch,kernel_modules,os_release", ["arch", "kernel_modules", "os_release"]),
        (
            "?fields[system_profile]=arch&fields[system_profile]=kernel_modules,os_release",
            ["arch", "kernel_modules", "os_release"],
        ),
    ),
)
def test_get_hosts_fields_param(query, fields, mocker, graphql_query_empty_response, api_get):
    url = build_hosts_url(query=query)
    response_status, response_data = api_get(url)

    assert response_status == 200

    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": mocker.ANY,
            "fields": fields,
        },
        mocker.ANY,
    )


@pytest.mark.parametrize("num_hosts", (1, 3, 5))
def test_get_hosts_by_ids(num_hosts, mocker, filtering_datetime_mock, graphql_query_empty_response, api_get):
    host_id_list = [generate_uuid() for h in range(num_hosts)]
    url = build_hosts_url(query=f"/{','.join(host_id_list)}")
    response_status, _ = api_get(url)

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
                    "stale_timestamp": {
                        "gt": "2019-12-02T10:10:06.754201+00:00",
                    },
                    "OR": [
                        {
                            "id": {"eq": host_id},
                        }
                        for host_id in host_id_list
                    ],
                },
            ),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


# Generic filtering tests
def _verify_hosts_query(mocker, graphql_query_empty_response, query):
    graphql_query_empty_response.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"OR": mocker.ANY}, query),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def _verify_tags_query(mocker, graphql_tag_query_empty_response, query):
    graphql_tag_query_empty_response.assert_called_once_with(
        TAGS_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "hostFilter": {"OR": mocker.ANY, "AND": (query,)},
        },
        mocker.ANY,
    )


def _verify_sap_system_query(mocker, graphql_system_profile_sap_system_query_empty_response, query):
    graphql_system_profile_sap_system_query_empty_response.assert_called_once_with(
        SAP_SYSTEM_QUERY,
        {"hostFilter": {"OR": mocker.ANY, "AND": (query,)}, "limit": mocker.ANY, "offset": mocker.ANY},
        mocker.ANY,
    )


def _verify_sap_sids_query(mocker, graphql_system_profile_sap_sids_query_empty_response, query):
    graphql_system_profile_sap_sids_query_empty_response.assert_called_once_with(
        SAP_SIDS_QUERY,
        {"hostFilter": {"OR": mocker.ANY, "AND": (query,)}, "limit": mocker.ANY, "offset": mocker.ANY},
        mocker.ANY,
    )


# Test generic filtering for string fields
def test_generic_filtering_string(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    filter_paths = (
        "[system_profile][rhc_client_id]",
        "[system_profile][rhc_config_state]",
        "[system_profile][bios_vendor]",
    )
    operations = ("", "[eq]")
    values = ("8dd97934-8ce4-11eb-8dcd-0242ac130003", "foo", "nil", "not_nil")
    rhc_client_id_queries = (
        {"spf_rhc_client_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_rhc_client_id": {"eq": "foo"}},
        {"spf_rhc_client_id": {"eq": None}},
        {"NOT": {"spf_rhc_client_id": {"eq": None}}},
    )
    rhc_config_state_queries = (
        {"spf_rhc_config_state": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_rhc_config_state": {"eq": "foo"}},
        {"spf_rhc_config_state": {"eq": None}},
        {"NOT": {"spf_rhc_config_state": {"eq": None}}},
    )
    bios_vendor = (
        {"spf_bios_vendor": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_bios_vendor": {"eq": "foo"}},
        {"spf_bios_vendor": {"eq": None}},
        {"NOT": {"spf_bios_vendor": {"eq": None}}},
    )
    query_dicts = (rhc_client_id_queries, rhc_config_state_queries, bios_vendor)

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        # build_system_profile_sap_sids_url
    )
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for path, queries in zip(filter_paths, query_dicts):
            for op in operations:
                for value, query in zip(values, queries):
                    with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                        url = url_builder(query=f"?filter{path}{op}={value}")

                        response_status, _ = api_get(url)

                        assert response_status == 200

                        query_verifier(mocker, query_mock, query)
                        query_mock.reset_mock()


# having both system_profile endpoints creates a mocking issue right now.
# Just going to split one off until I can refactor the whole test suite
def test_generic_filtering_string_sap_sids(
    mocker, subtests, graphql_system_profile_sap_sids_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = (
        "[system_profile][rhc_client_id]",
        "[system_profile][rhc_config_state]",
        "[system_profile][bios_vendor]",
    )
    operations = ("", "[eq]")
    values = ("8dd97934-8ce4-11eb-8dcd-0242ac130003", "foo", "nil", "not_nil")
    rhc_client_id_queries = (
        {"spf_rhc_client_id": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_rhc_client_id": {"eq": "foo"}},
        {"spf_rhc_client_id": {"eq": None}},
        {"NOT": {"spf_rhc_client_id": {"eq": None}}},
    )
    rhc_config_state_queries = (
        {"spf_rhc_config_state": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_rhc_config_state": {"eq": "foo"}},
        {"spf_rhc_config_state": {"eq": None}},
        {"NOT": {"spf_rhc_config_state": {"eq": None}}},
    )
    bios_vendor = (
        {"spf_bios_vendor": {"eq": "8dd97934-8ce4-11eb-8dcd-0242ac130003"}},
        {"spf_bios_vendor": {"eq": "foo"}},
        {"spf_bios_vendor": {"eq": None}},
        {"NOT": {"spf_bios_vendor": {"eq": None}}},
    )
    query_dicts = (rhc_client_id_queries, rhc_config_state_queries, bios_vendor)

    for path, queries in zip(filter_paths, query_dicts):
        for op in operations:
            for value, query in zip(values, queries):
                with subtests.test(value=value, query=query, path=path, endpoint="sap_sids"):
                    url = build_system_profile_sap_sids_url(query=f"?filter{path}{op}={value}")

                    response_status, _ = api_get(url)

                    assert response_status == 200

                    _verify_sap_sids_query(mocker, graphql_system_profile_sap_sids_query_empty_response, query)
                    graphql_system_profile_sap_sids_query_empty_response.reset_mock()


def test_generic_filtering_string_invalid_values(subtests, patch_xjoin_post, api_get):
    prefixes = (
        "?filter[system_profile][rhc_client_id]",
        "?filter[system_profile][rhc_config_state]",
        "?filter[system_profile][bios_vendor]",
    )
    suffixes = (
        "[foo]=bar",
        "[bar][]=bar",
        "[eq][foo]=bar",
        "[is]=bar",
        "[matches]=bar",
        "[lt]=bar",
        "[gt]=bar",
        "[lte]=bar",
        "[gte]=bar",
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        build_system_profile_sap_sids_url,
    )
    for url_builder in endpoint_url_builders:
        for prefix in prefixes:
            for suffix in suffixes:
                with subtests.test(prefix=prefix, suffix=suffix):
                    url = url_builder(query=prefix + suffix)
                    response_status, response_data = api_get(url)
                    assert response_status == 400
                    assert response_data["title"] == "Validation Error"


def test_generic_filtering_boolean(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    filter_paths = (
        "[system_profile][sap_system]",
        "[system_profile][satellite_managed]",
        "[system_profile][katello_agent_running]",
    )
    operations = ("", "[eq]")
    values = ("true", "false", "nil", "not_nil")
    sap_system_queries = (
        {"spf_sap_system": {"is": True}},
        {"spf_sap_system": {"is": False}},
        {"spf_sap_system": {"is": None}},
        {"NOT": {"spf_sap_system": {"is": None}}},
    )
    satellite_managed_queries = (
        {"spf_satellite_managed": {"is": True}},
        {"spf_satellite_managed": {"is": False}},
        {"spf_satellite_managed": {"is": None}},
        {"NOT": {"spf_satellite_managed": {"is": None}}},
    )
    katello_agent_running_queries = (
        {"spf_katello_agent_running": {"is": True}},
        {"spf_katello_agent_running": {"is": False}},
        {"spf_katello_agent_running": {"is": None}},
        {"NOT": {"spf_katello_agent_running": {"is": None}}},
    )
    query_dicts = (sap_system_queries, satellite_managed_queries, katello_agent_running_queries)

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for path, queries in zip(filter_paths, query_dicts):
            for op in operations:
                for value, query in zip(values, queries):
                    with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                        url = url_builder(query=f"?filter{path}{op}={value}")

                        response_status, _ = api_get(url)
                        assert response_status == 200

                        query_verifier(mocker, query_mock, query)
                        query_mock.reset_mock()


# having both system_profile endpoints creates a moching issue right now.
# Just going to split one off until I can refactor the whole test suite
def test_generic_filtering_boolean_sap_sids(
    mocker, subtests, graphql_system_profile_sap_sids_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = (
        "[system_profile][sap_system]",
        "[system_profile][satellite_managed]",
        "[system_profile][katello_agent_running]",
    )
    operations = ("", "[eq]")
    values = ("true", "false", "nil", "not_nil")
    sap_system_queries = (
        {"spf_sap_system": {"is": True}},
        {"spf_sap_system": {"is": False}},
        {"spf_sap_system": {"is": None}},
        {"NOT": {"spf_sap_system": {"is": None}}},
    )
    satellite_managed_queries = (
        {"spf_satellite_managed": {"is": True}},
        {"spf_satellite_managed": {"is": False}},
        {"spf_satellite_managed": {"is": None}},
        {"NOT": {"spf_satellite_managed": {"is": None}}},
    )
    katello_agent_running_queries = (
        {"spf_katello_agent_running": {"is": True}},
        {"spf_katello_agent_running": {"is": False}},
        {"spf_katello_agent_running": {"is": None}},
        {"NOT": {"spf_katello_agent_running": {"is": None}}},
    )
    query_dicts = (sap_system_queries, satellite_managed_queries, katello_agent_running_queries)

    for path, queries in zip(filter_paths, query_dicts):
        for op in operations:
            for value, query in zip(values, queries):
                with subtests.test(value=value, query=query, path=path, endpoint="sap_sids"):
                    url = build_system_profile_sap_sids_url(query=f"?filter{path}{op}={value}")

                    response_status, _ = api_get(url)

                    assert response_status == 200

                    _verify_sap_sids_query(mocker, graphql_system_profile_sap_sids_query_empty_response, query)
                    graphql_system_profile_sap_sids_query_empty_response.reset_mock()


def test_generic_filtering_booleans_invalid_values(subtests, patch_xjoin_post, api_get):
    prefixes = (
        "?filter[system_profile][sap_system]",
        "?filter[system_profile][satellite_managed]",
        "?filter[system_profile][katello_agent_running]",
    )
    suffixes = (
        # bad operation
        "[foo]=true",
        "[bar][]=true",
        "[eq][foo]=true",
        "[is]=true",
        "[lt]=true",
        "[gt]=true",
        "[lte]=true",
        "[gte]=true",
        "[matches]=true",
        "[contains]=true"
        # bad value
        "[eq]=foo",
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        build_system_profile_sap_sids_url,
    )
    for url_builder in endpoint_url_builders:
        for prefix in prefixes:
            for suffix in suffixes:
                with subtests.test(prefix=prefix, suffix=suffix):
                    url = url_builder(query=prefix + suffix)
                    response_status, response_data = api_get(url)
                    assert response_status == 400
                    assert response_data["title"] == "Validation Error"


def test_generic_filtering_integer_equality(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    filter_paths = (
        "[system_profile][number_of_cpus]",
        "[system_profile][number_of_sockets]",
        "[system_profile][system_memory_bytes]",
    )
    operations = ("", "[eq]")
    values = ("1", "18446744073709551615", "nil", "not_nil")
    number_of_cpus_queries = (
        {"spf_number_of_cpus": {"eq": 1}},
        {"spf_number_of_cpus": {"eq": 18446744073709551615}},
        {"spf_number_of_cpus": {"eq": None}},
        {"NOT": {"spf_number_of_cpus": {"eq": None}}},
    )
    number_of_sockets_queries = (
        {"spf_number_of_sockets": {"eq": 1}},
        {"spf_number_of_sockets": {"eq": 18446744073709551615}},
        {"spf_number_of_sockets": {"eq": None}},
        {"NOT": {"spf_number_of_sockets": {"eq": None}}},
    )
    system_memory_bytes_queries = (
        {"spf_system_memory_bytes": {"eq": 1}},
        {"spf_system_memory_bytes": {"eq": 18446744073709551615}},
        {"spf_system_memory_bytes": {"eq": None}},
        {"NOT": {"spf_system_memory_bytes": {"eq": None}}},
    )
    query_dicts = (number_of_cpus_queries, number_of_sockets_queries, system_memory_bytes_queries)

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for path, queries in zip(filter_paths, query_dicts):
            for op in operations:
                for value, query in zip(values, queries):
                    with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                        url = url_builder(query=f"?filter{path}{op}={value}")

                        response_status, _ = api_get(url)
                        assert response_status == 200

                        query_verifier(mocker, query_mock, query)
                        query_mock.reset_mock()


def test_generic_filtering_integer_range(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    filter_paths = (
        "[system_profile][number_of_cpus]",
        "[system_profile][number_of_sockets]",
        "[system_profile][system_memory_bytes]",
    )
    graphql_filters = ("spf_number_of_cpus", "spf_number_of_sockets", "spf_system_memory_bytes")
    api_operations = ("[lt]", "[lte]", "[gt]", "[gte]")
    graphql_operations = ("lt", "lte", "gt", "gte")
    values = ("1", "18446744073709551615")

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for path, graphql_filter in zip(filter_paths, graphql_filters):
            for api_operation, graphql_operation in zip(api_operations, graphql_operations):
                for value in values:
                    query = {graphql_filter: {graphql_operation: int(value)}}
                    with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                        url = url_builder(query=f"?filter{path}{api_operation}={value}")

                        response_status, _ = api_get(url)
                        assert response_status == 200

                        query_verifier(mocker, query_mock, query)
                        query_mock.reset_mock()


def test_generic_filtering_timestamp_equality(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    path = "[system_profile][last_boot_time]"

    operations = ("", "[eq]")
    values = ("2021-01-10T15:10:10.000Z", "nil", "not_nil")
    queries = (
        {"spf_last_boot_time": {"eq": "2021-01-10T15:10:10.000Z"}},
        {"spf_last_boot_time": {"eq": None}},
        {"NOT": {"spf_last_boot_time": {"eq": None}}},
    )

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for op in operations:
            for value, query in zip(values, queries):
                with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                    url = url_builder(query=f"?filter{path}{op}={value}")

                    response_status, _ = api_get(url)
                    assert response_status == 200

                    query_verifier(mocker, query_mock, query)
                    query_mock.reset_mock()


def test_generic_filtering_timestamp_range(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    path = "[system_profile][last_boot_time]"
    graphql_filter = "spf_last_boot_time"
    api_operations = ("[lt]", "[lte]", "[gt]", "[gte]")
    graphql_operations = ("lt", "lte", "gt", "gte")
    value = "2021-01-10T15:10:10.000Z"

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for api_operation, graphql_operation in zip(api_operations, graphql_operations):
            query = {graphql_filter: {graphql_operation: value}}
            with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                url = url_builder(query=f"?filter{path}{api_operation}={value}")

                response_status, _ = api_get(url)
                assert response_status == 200

                query_verifier(mocker, query_mock, query)
                query_mock.reset_mock()


# having both system_profile endpoints creates a mocking issue right now.
# Just going to split one off until I can refactor the whole test suite
def test_generic_filtering_integer_sap_sids(
    mocker, subtests, graphql_system_profile_sap_sids_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = (
        "[system_profile][number_of_cpus]",
        "[system_profile][number_of_sockets]",
        "[system_profile][system_memory_bytes]",
    )
    operations = ("", "[eq]")
    values = ("1", "18446744073709551615", "nil", "not_nil")
    number_of_cpus_queries = (
        {"spf_number_of_cpus": {"eq": 1}},
        {"spf_number_of_cpus": {"eq": 18446744073709551615}},
        {"spf_number_of_cpus": {"eq": None}},
        {"NOT": {"spf_number_of_cpus": {"eq": None}}},
    )
    number_of_sockets_queries = (
        {"spf_number_of_sockets": {"eq": 1}},
        {"spf_number_of_sockets": {"eq": 18446744073709551615}},
        {"spf_number_of_sockets": {"eq": None}},
        {"NOT": {"spf_number_of_sockets": {"eq": None}}},
    )
    system_memory_bytes_queries = (
        {"spf_system_memory_bytes": {"eq": 1}},
        {"spf_system_memory_bytes": {"eq": 18446744073709551615}},
        {"spf_system_memory_bytes": {"eq": None}},
        {"NOT": {"spf_system_memory_bytes": {"eq": None}}},
    )
    query_dicts = (number_of_cpus_queries, number_of_sockets_queries, system_memory_bytes_queries)

    for path, queries in zip(filter_paths, query_dicts):
        for op in operations:
            for value, query in zip(values, queries):
                with subtests.test(value=value, query=query, path=path, endpoint="sap_sids"):
                    url = build_system_profile_sap_sids_url(query=f"?filter{path}{op}={value}")

                    response_status, _ = api_get(url)

                    assert response_status == 200

                    _verify_sap_sids_query(mocker, graphql_system_profile_sap_sids_query_empty_response, query)
                    graphql_system_profile_sap_sids_query_empty_response.reset_mock()


def test_generic_filtering_integer_invalid_values(subtests, patch_xjoin_post, api_get):
    prefixes = (
        "?filter[system_profile][number_of_cpus]",
        "?filter[system_profile][number_of_sockets]",
        "?filter[system_profile][system_memory_bytes]",
    )
    suffixes = (
        # bad operation
        "[foo]=123",
        "[bar][]=123",
        "[eq][foo]=123",
        "[is]=123",
        "[matches]=123",
        "[contains]=123"
        # bad value
        "[eq]=foo",
        "[eq]=true",
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        build_system_profile_sap_sids_url,
    )
    for url_builder in endpoint_url_builders:
        for prefix in prefixes:
            for suffix in suffixes:
                with subtests.test(prefix=prefix, suffix=suffix):
                    url = url_builder(query=prefix + suffix)
                    response_status, response_data = api_get(url)
                    assert response_status == 400
                    assert response_data["title"] == "Validation Error"


def test_generic_filtering_timestamp_invalid_values(subtests, patch_xjoin_post, api_get):
    prefix = "?filter[system_profile][last_boot_time]"
    suffixes = (
        # bad operation
        "[foo]=123",
        "[bar][]=123",
        "[eq][foo]=123",
        "[is]=123",
        "[matches]=123",
        "[contains]=123"
        # bad value
        "[eq]=foo",
        "[eq]=true",
        "[eq]=123",
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        build_system_profile_sap_sids_url,
    )
    for url_builder in endpoint_url_builders:
        for suffix in suffixes:
            with subtests.test(prefix=prefix, suffix=suffix):
                url = url_builder(query=prefix + suffix)
                response_status, response_data = api_get(url)
                assert response_status == 400
                assert response_data["title"] == "Validation Error"


def test_generic_filtering_wildcard(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    filter_paths = ("[system_profile][insights_client_version]",)
    operations = ("", "[eq]")
    values = ("8.*", "7.3", "nil", "not_nil")
    insights_client_version_queries = (
        {"spf_insights_client_version": {"matches": "8.*"}},
        {"spf_insights_client_version": {"eq": "7.3"}},
        {"spf_insights_client_version": {"eq": None}},
        {"NOT": {"spf_insights_client_version": {"eq": None}}},
    )

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for path in filter_paths:
            for op in operations:
                for value, query in zip(values, insights_client_version_queries):
                    with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                        url = url_builder(query=f"?filter{path}{op}={value}")

                        response_status, _ = api_get(url)

                        assert response_status == 200

                        query_verifier(mocker, query_mock, query)
                        query_mock.reset_mock()


# having both system_profile endpoints creates a moching issue right now.
# Just going to split one off until I can refactor the whole test suite
def test_generic_filtering_wildcard_sap_sids(
    mocker, subtests, graphql_system_profile_sap_sids_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][insights_client_version]",)
    operations = ("", "[eq]")
    values = ("8.*", "7.3", "nil", "not_nil")
    insights_client_version_queries = (
        {"spf_insights_client_version": {"matches": "8.*"}},
        {"spf_insights_client_version": {"eq": "7.3"}},
        {"spf_insights_client_version": {"eq": None}},
        {"NOT": {"spf_insights_client_version": {"eq": None}}},
    )

    for path in filter_paths:
        for op in operations:
            for value, query in zip(values, insights_client_version_queries):
                with subtests.test(value=value, query=query, path=path, endpoint="sap_sids"):
                    url = build_system_profile_sap_sids_url(query=f"?filter{path}{op}={value}")

                    response_status, _ = api_get(url)

                    assert response_status == 200

                    _verify_sap_sids_query(mocker, graphql_system_profile_sap_sids_query_empty_response, query)
                    graphql_system_profile_sap_sids_query_empty_response.reset_mock()


def test_generic_filtering_wildcard_invalid_values(subtests, patch_xjoin_post, api_get):
    prefixes = ("?filter[system_profile][insights_client_version]",)
    suffixes = (
        # bad operation
        "[foo]=bar",
        "[bar][]=bar",
        "[eq][foo]=bar",
        "[is]=bar",
        "[lt]=bar",
        "[gt]=bar",
        "[lte]=bar",
        "[gte]=bar",
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        build_system_profile_sap_sids_url,
    )
    for url_builder in endpoint_url_builders:
        for prefix in prefixes:
            for suffix in suffixes:
                with subtests.test(url_builder=url_builder, prefix=prefix, suffix=suffix):
                    url = url_builder(query=prefix + suffix)
                    response_status, response_data = api_get(url)

                    assert response_status == 400
                    assert response_data["title"] == "Validation Error"


# Test generic filtering for object fields (the object itself, not its properties)
def test_generic_filtering_objects(
    mocker,
    subtests,
    graphql_query_empty_response,
    graphql_tag_query_empty_response,
    graphql_system_profile_sap_system_query_empty_response,
    patch_xjoin_post,
    api_get,
):
    filter_paths = ("[system_profile][ansible]", "[system_profile][mssql]")
    operations = ("", "[eq]")
    values = ("nil", "not_nil")
    ansible_queries = (
        {
            "spf_ansible": {
                "sso_version": {"eq": None},
                "hub_version": {"eq": None},
                "controller_version": {"eq": None},
                "catalog_worker_version": {"eq": None},
            }
        },
        {
            "NOT": {
                "spf_ansible": {
                    "sso_version": {"eq": None},
                    "hub_version": {"eq": None},
                    "controller_version": {"eq": None},
                    "catalog_worker_version": {"eq": None},
                }
            }
        },
    )
    mssql_queries = ({"spf_mssql": {"version": {"eq": None}}}, {"NOT": {"spf_mssql": {"version": {"eq": None}}}})
    query_dicts = (ansible_queries, mssql_queries)

    endpoints = ("hosts", "tags", "sap_system")
    endpoint_query_verifiers = (_verify_hosts_query, _verify_tags_query, _verify_sap_system_query)
    endpoint_query_mocks = (
        graphql_query_empty_response,
        graphql_tag_query_empty_response,
        graphql_system_profile_sap_system_query_empty_response,
    )
    endpoint_url_builders = (build_hosts_url, build_tags_url, build_system_profile_sap_system_url)
    for query_verifier, query_mock, endpoint, url_builder in zip(
        endpoint_query_verifiers, endpoint_query_mocks, endpoints, endpoint_url_builders
    ):
        for path, queries in zip(filter_paths, query_dicts):
            for op in operations:
                for value, query in zip(values, queries):
                    with subtests.test(value=value, query=query, path=path, endpoint=endpoint):
                        url = url_builder(query=f"?filter{path}{op}={value}")

                        response_status, _ = api_get(url)

                        assert response_status == 200

                        query_verifier(mocker, query_mock, query)
                        query_mock.reset_mock()


def test_generic_filtering_objects_sap_sids(
    mocker, subtests, graphql_system_profile_sap_sids_query_empty_response, patch_xjoin_post, api_get
):
    filter_paths = ("[system_profile][ansible]", "[system_profile][mssql]")
    operations = ("", "[eq]")
    values = ("nil", "not_nil")
    ansible_queries = (
        {
            "spf_ansible": {
                "sso_version": {"eq": None},
                "hub_version": {"eq": None},
                "controller_version": {"eq": None},
                "catalog_worker_version": {"eq": None},
            }
        },
        {
            "NOT": {
                "spf_ansible": {
                    "sso_version": {"eq": None},
                    "hub_version": {"eq": None},
                    "controller_version": {"eq": None},
                    "catalog_worker_version": {"eq": None},
                }
            }
        },
    )
    mssql_queries = ({"spf_mssql": {"version": {"eq": None}}}, {"NOT": {"spf_mssql": {"version": {"eq": None}}}})
    query_dicts = (ansible_queries, mssql_queries)

    for path, queries in zip(filter_paths, query_dicts):
        for op in operations:
            for value, query in zip(values, queries):
                with subtests.test(value=value, query=query, path=path, endpoint="sap_sids"):
                    url = build_system_profile_sap_sids_url(query=f"?filter{path}{op}={value}")

                    response_status, _ = api_get(url)

                    assert response_status == 200

                    _verify_sap_sids_query(mocker, graphql_system_profile_sap_sids_query_empty_response, query)
                    graphql_system_profile_sap_sids_query_empty_response.reset_mock()


def test_generic_filtering_objects_invalid_values(subtests, patch_xjoin_post, api_get):
    prefixes = ("?filter[system_profile][ansible]",)
    suffixes = (
        # bad operation
        "[foo]=bar",
        "[bar][]=bar",
        "[eq][foo]=bar",
        "[is]=bar",
        "[lt]=bar",
        "[gt]=bar",
        "[lte]=bar",
        "[gte]=bar",
        # bad value
        "=foo",
    )
    endpoint_url_builders = (
        build_hosts_url,
        build_tags_url,
        build_system_profile_sap_system_url,
        build_system_profile_sap_sids_url,
    )
    for url_builder in endpoint_url_builders:
        for prefix in prefixes:
            for suffix in suffixes:
                with subtests.test(prefix=prefix, suffix=suffix):
                    url = url_builder(query=prefix + suffix)
                    response_status, response_data = api_get(url)

                    assert response_status == 400
                    assert response_data["title"] == "Validation Error"
