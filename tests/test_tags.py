import pytest
from sqlalchemy import null

from app.models import ProviderType
from lib.host_repository import find_hosts_by_staleness
from lib.host_repository import find_non_culled_hosts
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import api_tags_count_pagination_test
from tests.helpers.api_utils import api_tags_pagination_test
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_tags_count_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.db_utils import update_host_in_db
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import SYSTEM_IDENTITY


def test_get_tags_of_multiple_hosts(mq_create_four_specific_hosts, api_get, subtests):
    """
    Send a request for the tag count of 1 host and check
    that it is the correct number
    """
    created_hosts = mq_create_four_specific_hosts
    expected_response = {host.id: host.tags for host in created_hosts}

    url = build_host_tags_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response) == len(response_data["results"])

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response))


def test_get_tag_count_of_multiple_hosts(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    expected_response = {host.id: len(host.tags) for host in created_hosts}

    url = build_tags_count_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response) == len(response_data["results"])

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response))


def test_get_tags_of_hosts_that_doesnt_exist(mq_create_four_specific_hosts, api_get):
    """
    send a request for some hosts that don't exist
    """
    host_id = "fa28ec9b-5555-4b96-9b72-96129e0c3336"
    url = build_host_tags_url(host_id)
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
    ):
        with subtests.test(query=query):
            url = build_tags_url(query=query)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)
            assert response_data["total"] == 1


def test_get_filtered_by_search_tags_of_multiple_hosts(mq_create_four_specific_hosts, api_get, subtests):
    """
    send a request for tags to one host with some searchTerm
    """
    created_hosts = mq_create_four_specific_hosts

    for search, results in (
        (
            "",
            {
                created_hosts[0].id: [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                    {"namespace": "SPECIAL", "key": "tag", "value": "ToFind"},
                    {"namespace": "no", "key": "key", "value": None},
                ],
                created_hosts[1].id: [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
                created_hosts[2].id: [
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                    {"namespace": "NS1", "key": "key3", "value": "val3"},
                    {"namespace": None, "key": "key4", "value": "val4"},
                    {"namespace": None, "key": "key5", "value": None},
                ],
                created_hosts[3].id: [],
            },
        ),
        (
            "To",
            {
                created_hosts[0].id: [{"namespace": "SPECIAL", "key": "tag", "value": "ToFind"}],
                created_hosts[1].id: [],
                created_hosts[2].id: [],
                created_hosts[3].id: [],
            },
        ),
        (
            "NS1",
            {
                created_hosts[0].id: [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                ],
                created_hosts[1].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                created_hosts[2].id: [{"namespace": "NS1", "key": "key3", "value": "val3"}],
                created_hosts[3].id: [],
            },
        ),
        (
            "key1",
            {
                created_hosts[0].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                created_hosts[1].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                created_hosts[2].id: [],
                created_hosts[3].id: [],
            },
        ),
        (
            "val1",
            {
                created_hosts[0].id: [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                ],
                created_hosts[1].id: [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                created_hosts[2].id: [],
                created_hosts[3].id: [],
            },
        ),
        (
            "e",
            {
                created_hosts[0].id: [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                    {"namespace": "no", "key": "key", "value": None},
                ],
                created_hosts[1].id: [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
                created_hosts[2].id: [
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                    {"namespace": "NS1", "key": "key3", "value": "val3"},
                    {"namespace": None, "key": "key4", "value": "val4"},
                    {"namespace": None, "key": "key5", "value": None},
                ],
                created_hosts[3].id: [],
            },
        ),
        (" ", {created_hosts[0].id: [], created_hosts[1].id: [], created_hosts[2].id: [], created_hosts[3].id: []}),
    ):
        with subtests.test(search=search):
            url = build_host_tags_url(host_list_or_id=created_hosts, query=f"?search={search}")
            response_status, response_data = api_get(url)

            assert response_status == 200
            assert len(results.keys()) == len(response_data["results"].keys())
            for host_id, tags in results.items():
                assert len(tags) == len(response_data["results"][host_id])


def test_get_tags_count_of_hosts_that_doesnt_exist(mq_create_four_specific_hosts, api_get):
    """
    send a request for some hosts that don't exist
    """
    host_id = "fa28ec9b-5555-4b96-9b72-96129e0c3336"
    url = build_tags_count_url(host_list_or_id=host_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {} == response_data["results"]


def test_get_tags_from_host_with_no_tags(mq_create_four_specific_hosts, api_get):
    """
    send a request for a host with no tags
    """
    created_hosts = mq_create_four_specific_hosts

    host_with_no_tags = created_hosts[3]
    expected_response = {host_with_no_tags.id: []}

    url = build_host_tags_url(host_list_or_id=host_with_no_tags.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response) == len(response_data["results"])


@pytest.mark.parametrize("tags", (None, null()))
def test_get_tags_from_host_with_null_tags(tags, mq_create_four_specific_hosts, api_get):
    # FIXME: Remove this test after migration to NOT NULL.
    created_hosts = mq_create_four_specific_hosts

    host_id = created_hosts[0].id
    update_host_in_db(host_id, tags=tags)

    url = build_host_tags_url(host_list_or_id=host_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {host_id: []} == response_data["results"]


@pytest.mark.parametrize("tags", (None, null()))
def test_get_tags_count_from_host_with_null_tags(tags, mq_create_four_specific_hosts, api_get):
    # FIXME: Remove this test after migration to NOT NULL.
    created_hosts = mq_create_four_specific_hosts

    host_id = created_hosts[0].id
    update_host_in_db(host_id, tags=tags)

    url = build_tags_count_url(host_list_or_id=host_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {host_id: 0} == response_data["results"]


def test_get_tags_count_from_host_with_no_tags(mq_create_four_specific_hosts, api_get):
    """
    send a request for a host with no tags
    """
    created_hosts = mq_create_four_specific_hosts
    host_with_no_tags = created_hosts[3]

    url = build_tags_count_url(host_list_or_id=host_with_no_tags.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {host_with_no_tags.id: 0} == response_data["results"]


def test_get_tags_count_from_host_with_tag_with_no_value(mq_create_four_specific_hosts, api_get):
    """
    host 0 has 4 tags, one of which has no value
    """
    created_hosts = mq_create_four_specific_hosts
    host_with_valueless_tag = created_hosts[0]

    url = build_tags_count_url(host_list_or_id=host_with_valueless_tag.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert {host_with_valueless_tag.id: 4} == response_data["results"]


def test_tags_pagination(mq_create_four_specific_hosts, api_get, subtests):
    """
    simple test to check pagination works for /tags
    """
    created_hosts = mq_create_four_specific_hosts
    expected_responses_1_per_page = [{host.id: host.tags} for host in created_hosts]

    url = build_host_tags_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")

    # 1 per page test
    api_tags_pagination_test(api_get, subtests, url, len(created_hosts), 1, expected_responses_1_per_page)

    expected_responses_2_per_page = [
        {created_hosts[0].id: created_hosts[0].tags, created_hosts[1].id: created_hosts[1].tags},
        {created_hosts[2].id: created_hosts[2].tags, created_hosts[3].id: created_hosts[3].tags},
    ]

    # 2 per page test
    api_tags_pagination_test(api_get, subtests, url, len(created_hosts), 2, expected_responses_2_per_page)


def test_tags_count_pagination(mq_create_four_specific_hosts, api_get, subtests):
    """
    simple test to check pagination works for /tags
    """
    created_hosts = mq_create_four_specific_hosts
    expected_responses_1_per_page = [{host.id: len(host.tags)} for host in created_hosts]

    url = build_tags_count_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")

    # 1 per page test
    api_tags_count_pagination_test(api_get, subtests, url, len(created_hosts), 1, expected_responses_1_per_page)

    expected_responses_2_per_page = [
        {created_hosts[0].id: len(created_hosts[0].tags), created_hosts[1].id: len(created_hosts[1].tags)},
        {created_hosts[2].id: len(created_hosts[2].tags), created_hosts[3].id: len(created_hosts[3].tags)},
    ]

    # 2 per page test
    api_tags_count_pagination_test(api_get, subtests, url, len(created_hosts), 2, expected_responses_2_per_page)


def test_get_host_tags_with_RBAC_allowed(subtests, mocker, db_create_host, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_host_tags_url(host_list_or_id=host.id)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)


def test_get_host_tags_with_RBAC_denied(subtests, mocker, db_create_host, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_hosts_by_staleness_mock = mocker.patch(
        "lib.host_repository.find_hosts_by_staleness", wraps=find_hosts_by_staleness
    )

    for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_host_tags_url(host_list_or_id=host.id)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 403)

            find_hosts_by_staleness_mock.assert_not_called()


def test_get_host_tag_count_RBAC_allowed(mq_create_four_specific_hosts, mocker, api_get, subtests, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    created_hosts = mq_create_four_specific_hosts

    expected_response = {host.id: len(host.tags) for host in created_hosts}

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
            response_status, response_data = api_get(url)

            assert response_status == 200
            assert len(expected_response) == len(response_data["results"])

            api_pagination_test(api_get, subtests, url, expected_total=len(expected_response))


def test_get_host_tag_count_RBAC_denied(mq_create_four_specific_hosts, mocker, api_get, subtests, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_non_culled_hosts_mock = mocker.patch("lib.host_repository.find_non_culled_hosts", wraps=find_non_culled_hosts)

    created_hosts = mq_create_four_specific_hosts

    for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
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
