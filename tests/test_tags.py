from datetime import timedelta

import pytest

from app.models import ProviderType
from app.serialization import _deserialize_tags_dict
from lib.host_repository import find_hosts_by_staleness
from lib.host_repository import find_non_culled_hosts
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_tags_count_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now


@pytest.mark.parametrize(
    "search",
    (
        "&search=NS1",
        "&search=NS1/key2=val1",
    ),
)
def test_get_tags_of_multiple_hosts_query_via_db(mq_create_three_specific_hosts, api_get, search):
    """
    Send a request for the tag count of multiple hosts and validate the query
    """
    created_hosts = mq_create_three_specific_hosts

    url = build_host_tags_url(host_list_or_id=created_hosts, query=f"?order_by=updated&order_how=ASC{search}")
    response_status, response = api_get(url)
    assert response_status == 200
    assert response["count"] == len(created_hosts)
    assert response["results"][created_hosts[0].id] != {}


def test_host_tag_response_and_pagination_via_db(mq_create_three_specific_hosts, api_get):
    """
    Given a set host creation, verify that the tags URL returns data correctly.
    """
    created_hosts = mq_create_three_specific_hosts

    url = build_host_tags_url(host_list_or_id=mq_create_three_specific_hosts, query="?order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == len(created_hosts)
    assert response_data["page"] == 1
    assert response_data["per_page"] == 50  # The default value, since we didn't specify


def test_host_tags_via_db_invalid_updated_params(api_get):
    """
    Test using an updated_start that's later than updated_end
    """

    query_params = "?updated_start=2024-01-19T15:00:00.000Z&updated_end=2024-01-15T09:00:00.000Z"
    url = build_tags_url(query=query_params)
    response_status, _ = api_get(url)
    assert response_status == 400


def test_get_tags_of_hosts_that_does_not_exist_via_db(api_get):
    """
    send a request for some host that doesn't exist
    """
    url = build_host_tags_url(generate_uuid())

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {}


def test_get_list_of_tags_with_host_filters_via_db(db_create_multiple_hosts, api_get, subtests):
    """
    Validate that the /tags endpoint doesn't break when we supply it with various filters.
    """
    _now = now()
    insights_id = generate_uuid()
    provider_id = generate_uuid()
    display_name = "test-example-host"
    namespace = "ns1"
    tag_key = "database"
    tag_value = "postgresql"
    per_reporter_staleness = {
        "puptoo": {
            "last_check_in": _now.isoformat(),
            "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
            "check_in_succeeded": True,
        },
        "yupana": {
            "last_check_in": (_now - timedelta(days=3)).isoformat(),
            "stale_timestamp": (_now + timedelta(days=4)).isoformat(),
            "check_in_succeeded": True,
        },
    }
    db_create_multiple_hosts(
        how_many=1,
        extra_data={
            "canonical_facts": {
                "insights_id": insights_id,
                "provider_type": ProviderType.AZURE.value,
                "provider_id": provider_id,
            },
            "display_name": display_name,
            "tags": _deserialize_tags_dict({namespace: {tag_key: [tag_value]}}),
            "per_reporter_staleness": per_reporter_staleness,
        },
    )

    for test_case in (
        {"query": f"?display_name={display_name}", "expected_count": 1},
        {"query": f"?insights_id={insights_id}", "expected_count": 1},
        {"query": f"?provider_id={provider_id}", "expected_count": 1},
        {"query": f"?provider_type={ProviderType.AZURE.value}", "expected_count": 1},
        {"query": f"?search={tag_key}", "expected_count": 1},
        {"query": f"?search={tag_key.swapcase()}", "expected_count": 1},
        {"query": f"?search={namespace}/{tag_key}={tag_value}", "expected_count": 1},
        {"query": "?search=not-found", "expected_count": 0},
        {"query": "?registered_with=puptoo", "expected_count": 1},
        {"query": "?registered_with=yupana", "expected_count": 1},
        {"query": "?staleness=fresh", "expected_count": 1},
    ):
        with subtests.test(query=test_case.get("query")):
            url = build_tags_url(query=test_case.get("query"))
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)
            assert response_data["total"] == test_case.get("expected_count")
            if test_case.get("expected_count") == 1:
                assert response_data["results"][0]["tag"]["namespace"] == namespace
                assert response_data["results"][0]["tag"]["key"] == tag_key
                assert response_data["results"][0]["tag"]["value"] == tag_value
                assert response_data["results"][0]["count"] == 1


@pytest.mark.usefixtures("subtests")
def test_get_tags_invalid_start_end(api_get):
    """
    Validate that the /tags endpoint properly handles updated_start and updated_end validation errors.
    """

    url = build_tags_url(query="?updated_start=2022-01-19T15:00:00.000Z&updated_end=2020-01-19T15:00:00.000Z")
    response_status, _ = api_get(url)

    assert_response_status(response_status, 400)


def test_get_tags_count_of_host_that_does_not_exist(api_get):
    """
    send a request for some host that doesn't exist
    """
    url = build_tags_count_url(host_list_or_id=generate_uuid())
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {}


def test_get_tags_from_host_with_no_tags(api_get, db_create_host):
    """
    send a request for a host with no tags
    """
    host_with_no_tags_id = str(db_create_host().id)

    url = build_host_tags_url(host_list_or_id=host_with_no_tags_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {host_with_no_tags_id: []}


def test_get_tags_count_from_host_with_no_tags(api_get, db_create_host):
    """
    send a request for a host with no tags
    """
    host_with_no_tags_id = str(db_create_host().id)

    url = build_tags_count_url(host_list_or_id=host_with_no_tags_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {host_with_no_tags_id: 0}


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tags_with_RBAC_allowed(subtests, mocker, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_host_tags_url(host_list_or_id=generate_uuid())
            response_status, _ = api_get(url)

            assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tags_with_RBAC_denied(subtests, mocker, api_get):
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


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tag_count_RBAC_allowed(mocker, api_get, subtests, mq_create_three_specific_hosts):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    host_list = mq_create_three_specific_hosts
    expected_response = {host.id: len(host.tags) for host in host_list}

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=host_list, query="?order_by=updated&order_how=ASC")
            response_status, response_data = api_get(url)

            assert response_status == 200
            assert len(expected_response) == len(response_data["results"])


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tag_count_RBAC_denied(mq_create_four_specific_hosts, mocker, api_get, subtests):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_non_culled_hosts_mock = mocker.patch("lib.host_repository.find_non_culled_hosts", wraps=find_non_culled_hosts)

    created_hosts = mq_create_four_specific_hosts

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
            response_status, _ = api_get(url)

            assert response_status == 403

            find_non_culled_hosts_mock.assert_not_called()


def test_get_tags_count_of_host_that_does_not_exist_via_db(api_get):
    """
    send a request for some host that doesn't exist via db only
    """
    url = build_tags_count_url(host_list_or_id=generate_uuid())
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {}


def test_get_tags_count_of_host_via_db(api_get, mq_create_three_specific_hosts):
    """
    send a request for some host that does exist via db only
    """
    created_hosts = mq_create_three_specific_hosts
    url = build_tags_count_url(host_list_or_id=created_hosts[0].id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"][created_hosts[0].id] >= 0


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tags_with_RBAC_bypassed_as_system(db_create_host, api_get):
    host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": generate_uuid()}})

    url = build_host_tags_url(host_list_or_id=host.id)
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


@pytest.mark.parametrize(
    "null_value_tag,flattened_tag",
    (
        (
            {"ns1": {"key1": None}},
            {"namespace": "ns1", "key": "key1", "value": None},
        ),
        (
            {"insights-client": {"ABaOUCuGU": []}},
            {"namespace": "insights-client", "key": "ABaOUCuGU", "value": None},
        ),
    ),
)
def test_get_host_tags_null_value_via_db(api_get, db_create_host, null_value_tag, flattened_tag):
    created_host = db_create_host(extra_data={"tags": null_value_tag})

    url = build_host_tags_url(host_list_or_id=created_host.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag in response_data["results"][str(created_host.id)]

    url = build_tags_url()
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag == response_data["results"][0]["tag"]


def test_get_host_tags_null_namespace_via_db(api_get, db_create_host):
    null_namespace_tag = {None: {"key1": "val1"}}
    flattened_tag = {"namespace": None, "key": "key1", "value": "val1"}
    created_host = db_create_host(extra_data={"tags": null_namespace_tag})

    url = build_host_tags_url(host_list_or_id=created_host.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag in response_data["results"][str(created_host.id)]


@pytest.mark.parametrize(
    "tag, flattened_tag",
    (
        (
            {"insights-client": {"char-$-in-key": "50"}},
            {"namespace": "insights-client", "key": "char-$-in-key", "value": "50"},
        ),
        (
            {"insights-client": {"test-key": "char-$-in-value"}},
            {"namespace": "insights-client", "key": "test-key", "value": "char-$-in-value"},
        ),
    ),
)
def test_get_tags_with_dollar_signs_via_db(api_get, db_create_host, tag, flattened_tag):
    db_create_host(extra_data={"tags": tag})

    url = build_tags_url(query="?search=char-$-in")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag == response_data["results"][0]["tag"]
