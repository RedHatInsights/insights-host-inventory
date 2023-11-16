from api.host_query_xjoin import HOST_TAGS_QUERY
from app.models import ProviderType
from app.serialization import _deserialize_tags
from lib.host_repository import find_hosts_by_staleness
from lib.host_repository import find_non_culled_hosts
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_tags_count_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.graphql_utils import EMPTY_HOSTS_RESPONSE
from tests.helpers.graphql_utils import XJOIN_HOSTS_NO_TAGS_RESPONSE
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE_WITH_TAGS
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import SYSTEM_IDENTITY


def test_get_tags_of_multiple_hosts_query(
    mq_create_three_specific_hosts, api_get, mocker, graphql_query_empty_response
):
    """
    Send a request for the tag count of multiple hosts and validate the xjoin query
    """
    created_hosts = mq_create_three_specific_hosts

    url = build_host_tags_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
    response_status, _ = api_get(url)

    assert response_status == 200
    graphql_query_empty_response.assert_called_once_with(
        HOST_TAGS_QUERY,
        {
            "order_by": "modified_on",
            "order_how": "ASC",
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": {
                "OR": mocker.ANY,
                "AND": ({"OR": [{"id": {"eq": host.id}} for host in created_hosts]},),
            },
        },
        mocker.ANY,
    )


def test_host_tag_response_and_pagination(mq_create_three_specific_hosts, api_get, patch_xjoin_post):
    """
    Given a set response from xjoin, verify that the tags URL returns data correctly.
    """
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE_WITH_TAGS})

    url = build_host_tags_url(host_list_or_id=mq_create_three_specific_hosts, query="?order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == len(XJOIN_HOSTS_RESPONSE_WITH_TAGS["hosts"]["data"])
    assert response_data["page"] == 1
    assert response_data["per_page"] == 50  # The default value, since we didn't specify


def test_tag_counting_and_pagination(mq_create_three_specific_hosts, api_get, patch_xjoin_post):
    """
    Given a set response from xjoin, verify that the tag count URL returns data correctly.
    """
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE_WITH_TAGS})

    url = build_tags_count_url(host_list_or_id=mq_create_three_specific_hosts, query="?order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == len(XJOIN_HOSTS_RESPONSE_WITH_TAGS["hosts"]["data"])
    assert response_data["page"] == 1
    assert response_data["per_page"] == 50  # The default value, since we didn't specify


def test_get_tags_of_hosts_that_does_not_exist(api_get, patch_xjoin_post):
    """
    send a request for some host that doesn't exist
    """
    patch_xjoin_post(response={"data": EMPTY_HOSTS_RESPONSE})

    url = build_host_tags_url("fa28ec9b-5555-4b96-9b72-96129e0c3336")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {} == response_data["results"]


def test_get_list_of_tags_with_host_filters(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={"data": {"hostTags": {"meta": {"total": 1}, "data": []}}})
    """
    Validate that the /tags endpoint doesn't break when we supply it with various filters.
    We test the actual xjoin call in test_xjoin.test_tags_query_host_filters.
    """
    for query in (
        "?display_name=test-example-host",
        "?fqdn=tagfilter.test.com",
        "?hostname_or_id=test-example-host",
        "?hostname_or_id=tagfilter.test.com",
        f"?insights_id={generate_uuid()}",
        f"?provider_id={generate_uuid()}",
        f"?provider_type={ProviderType.AZURE.value}",
        "?updated_start=2020-01-19T15:00:00.000Z",
        "?updated_end=2022-02-08T09:00:00.000Z",
        "?updated_start=2022-01-19T15:00:00.000Z&updated_end=2022-01-19T15:00:00.000Z",
        "?group_name=coolgroup",
    ):
        with subtests.test(query=query):
            url = build_tags_url(query=query)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)
            assert response_data["total"] == 1


def test_get_tags_invalid_start_end(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={"data": {"hostTags": {"meta": {"total": 1}, "data": []}}})
    """
    Validate that the /tags endpoint properly handles updated_start and updated_end validation errors.
    """

    url = build_tags_url(query="?updated_start=2022-01-19T15:00:00.000Z&updated_end=2020-01-19T15:00:00.000Z")
    response_status, _ = api_get(url)

    assert_response_status(response_status, 400)


def test_get_filtered_by_search_tags_of_multiple_hosts(api_get, patch_xjoin_post, mocker, subtests):
    """
    send a request for tags to one host with some searchTerm
    """
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE_WITH_TAGS})
    host_list = XJOIN_HOSTS_RESPONSE_WITH_TAGS["hosts"]["data"]
    for search, results in (
        (
            "",
            {
                host_list[0]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "dev"},
                    {"namespace": "insights-client", "key": "database", "value": None},
                    {"namespace": "insights-client", "key": "os", "value": "fedora"},
                ],
                host_list[1]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "stage"},
                    {"namespace": "insights-client", "key": "os", "value": "macos"},
                ],
                host_list[2]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "prod"},
                ],
            },
        ),
        (
            "env",
            {
                host_list[0]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "dev"},
                ],
                host_list[1]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "stage"},
                ],
                host_list[2]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "prod"},
                ],
            },
        ),
        (
            "prod",
            {
                host_list[0]["id"]: [],
                host_list[1]["id"]: [],
                host_list[2]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "prod"},
                ],
            },
        ),
        (
            "insights",
            {
                host_list[0]["id"]: [
                    {"namespace": "insights-client", "key": "database", "value": None},
                    {"namespace": "insights-client", "key": "os", "value": "fedora"},
                ],
                host_list[1]["id"]: [
                    {"namespace": "insights-client", "key": "os", "value": "macos"},
                ],
                host_list[2]["id"]: [],
            },
        ),
        (
            "e",
            {
                host_list[0]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "dev"},
                    {"namespace": "insights-client", "key": "database", "value": None},
                    {"namespace": "insights-client", "key": "os", "value": "fedora"},
                ],
                host_list[1]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "stage"},
                    {"namespace": "insights-client", "key": "os", "value": "macos"},
                ],
                host_list[2]["id"]: [
                    {"namespace": "Sat", "key": "env", "value": "prod"},
                ],
            },
        ),
        (" ", {host_list[0]["id"]: [], host_list[1]["id"]: [], host_list[2]["id"]: []}),
    ):
        with subtests.test(search=search, xjoin_query=results):
            host_id = generate_uuid()
            url = build_host_tags_url(host_list_or_id=host_id, query=f"?search={search}")
            response_status, response_data = api_get(url)

            assert response_status == 200

            # Assert that the appropriate tags are filtered out in the response
            assert response_data["results"] == results


def test_get_tags_count_of_host_that_does_not_exist(api_get, patch_xjoin_post):
    """
    send a request for some host that doesn't exist
    """
    patch_xjoin_post(response={"data": EMPTY_HOSTS_RESPONSE})
    url = build_tags_count_url(host_list_or_id="fa28ec9b-5555-4b96-9b72-96129e0c3336")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {} == response_data["results"]


def test_get_tags_from_host_with_no_tags(api_get, patch_xjoin_post):
    """
    send a request for a host with no tags
    """
    patch_xjoin_post(response={"data": XJOIN_HOSTS_NO_TAGS_RESPONSE})
    host_with_no_tags_id = XJOIN_HOSTS_NO_TAGS_RESPONSE["hosts"]["data"][0]["id"]

    expected_response = {host_with_no_tags_id: []}

    url = build_host_tags_url(host_list_or_id=host_with_no_tags_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response) == len(response_data["results"])


def test_get_tags_count_from_host_with_no_tags(api_get, patch_xjoin_post):
    """
    send a request for a host with no tags
    """
    patch_xjoin_post(response={"data": XJOIN_HOSTS_NO_TAGS_RESPONSE})
    host_with_no_tags_id = XJOIN_HOSTS_NO_TAGS_RESPONSE["hosts"]["data"][0]["id"]

    url = build_tags_count_url(host_list_or_id=host_with_no_tags_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {host_with_no_tags_id: 0} == response_data["results"]


def test_get_tags_count_from_host_with_tag_with_no_value(api_get, patch_xjoin_post):
    """
    host 0 has 4 tags, one of which has no value
    """
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE_WITH_TAGS})
    host_with_no_value_tag_id = XJOIN_HOSTS_NO_TAGS_RESPONSE["hosts"]["data"][0]["id"]

    url = build_tags_count_url(host_list_or_id=host_with_no_value_tag_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"][host_with_no_value_tag_id] == 3


def test_get_host_tags_with_RBAC_allowed(subtests, mocker, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_host_tags_url(host_list_or_id=generate_uuid())
            response_status, _ = api_get(url)

            assert_response_status(response_status, 200)


def test_get_host_tags_with_RBAC_denied(subtests, mocker, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_hosts_by_staleness_mock = mocker.patch(
        "lib.host_repository.find_hosts_by_staleness", wraps=find_hosts_by_staleness
    )

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_host_tags_url(host_list_or_id=generate_uuid())
            response_status, _ = api_get(url)

            assert_response_status(response_status, 403)

            find_hosts_by_staleness_mock.assert_not_called()


def test_get_host_tag_count_RBAC_allowed(mocker, api_get, subtests, patch_xjoin_post, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE_WITH_TAGS})
    host_list = []
    for host in XJOIN_HOSTS_RESPONSE_WITH_TAGS["hosts"]["data"]:
        new_host = minimal_db_host(tags=_deserialize_tags(host["tags"]["data"]))
        new_host.id = host["id"]
        host_list.append(new_host)

    expected_response = {host.id: len(host.tags) for host in host_list}

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=host_list, query="?order_by=updated&order_how=ASC")
            response_status, response_data = api_get(url)

            assert response_status == 200
            assert len(expected_response) == len(response_data["results"])


def test_get_host_tag_count_RBAC_denied(mq_create_four_specific_hosts, mocker, api_get, subtests, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_non_culled_hosts_mock = mocker.patch("lib.host_repository.find_non_culled_hosts", wraps=find_non_culled_hosts)

    created_hosts = mq_create_four_specific_hosts

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
            response_status, response_data = api_get(url)

            assert response_status == 403

            find_non_culled_hosts_mock.assert_not_called()


def test_get_host_tags_with_RBAC_bypassed_as_system(db_create_host, api_get, enable_rbac):
    host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": generate_uuid()}})

    url = build_host_tags_url(host_list_or_id=host.id)
    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


def test_get_tags_sap_system(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={"data": {"hostTags": {"meta": {"total": 1}, "data": []}}})

    values = ("true", "false", "nil", "not_nil")

    for value in values:
        with subtests.test(value=value):
            implicit_url = build_tags_url(query=f"?filter[system_profile][sap_system]={value}")
            eq_url = build_tags_url(query=f"?filter[system_profile][sap_system][eq]={value}")

            implicit_response_status, implicit_response_data = api_get(implicit_url)
            eq_response_status, eq_response_data = api_get(eq_url)

            assert_response_status(implicit_response_status, 200)
            assert_response_status(eq_response_status, 200)
            assert implicit_response_data["total"] == 1
            assert eq_response_data["total"] == 1


def test_get_tags_sap_sids(patch_xjoin_post, api_get, subtests):
    patch_xjoin_post(response={"data": {"hostTags": {"meta": {"total": 1}, "data": []}}})

    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("ABC",), ("BEN", "A72"), ("CDA", "MK2", "C2C"))

    for path in filter_paths:
        for values in value_sets:
            with subtests.test(values=values, path=path):
                url = build_tags_url(query="?" + "".join([f"filter{path}={value}&" for value in values]))

                response_status, response_data = api_get(url)

                assert_response_status(response_status, 200)
                assert response_data["total"] == 1
