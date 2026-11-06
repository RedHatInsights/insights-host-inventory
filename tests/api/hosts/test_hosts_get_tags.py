import pytest

from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import minimal_host


@pytest.mark.parametrize(
    "tag_query,part_name",
    (
        (f"{'a' * 256}/key=val", "namespace"),
        (f"namespace/{'a' * 256}=val", "key"),
        (f"namespace/key={'a' * 256}", "value"),
    ),
)
def test_get_host_tag_part_too_long(tag_query, part_name, api_get):
    """
    send a request to find hosts with a string tag where the length
    of the namespace excedes the 255 character limit
    """

    url = build_hosts_url(query=f"?tags={tag_query}")
    _, response_data = api_get(url)

    assert_error_response(
        response_data, expected_status=400, expected_detail=f"{part_name} is longer than 255 characters"
    )


def test_get_host_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=SPECIAL/tag=ToFind")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_multiple_hosts_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0], created_hosts[1]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&order_by=updated&order_how=ASC")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_by_multiple_tags(db_create_host, api_get, subtests):
    """
    Get only the host that has all requested tags (AND semantics across different identities),
    and not the other hosts which only have some of the tags we query for.
    """
    tags_data_list = [
        {"tags": {"ns1": {"key1": ["val1"]}}},
        {"tags": {"ns1": {"key1": ["val1"], "key2": ["val2"]}}},
        {"tags": {"ns1": {"key1": ["val1"], "key3": ["val3"]}}},
        {"tags": {"ns1": {"key3": ["val3"], "key4": ["val4"]}}},
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=ns1/key1=val1&tags=ns1/key2=val2")

    api_pagination_test(api_get, subtests, url, expected_total=1)
    _, response_data = api_get(url)

    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host_ids[1]


def test_get_host_by_subset_of_tags(mq_create_three_specific_hosts, api_get, subtests):
    """
    Get a host using a subset of its tags
    """
    created_host_ids = [str(host.id) for host in mq_create_three_specific_hosts]
    url = build_hosts_url(query="?tags=NS1/key1=val1&tags=NS3/key3=val3")

    api_pagination_test(api_get, subtests, url, expected_total=1)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == created_host_ids[1]


def test_get_host_by_same_identity_tags_uses_or(db_create_host, api_get, subtests):
    """
    Verify OR logic for tags sharing the same identity (same namespace and key).
    """
    tags_data_list = [
        {"tags": {"ns1": {"key1": ["val1"]}}},
        {"tags": {"ns1": {"key1": ["val2"]}}},
        {"tags": {"ns1": {"key1": ["val3"]}}},
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=ns1/key1=val1&tags=ns1/key1=val2")

    api_pagination_test(api_get, subtests, url, expected_total=2)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    result_ids = {result["id"] for result in response_data["results"]}
    assert result_ids == {host_ids[0], host_ids[1]}


def test_get_host_by_different_identity_tags_uses_and(db_create_host, api_get, subtests):
    """
    Verify AND logic for tags with different identities (different namespace or key).
    """
    tags_data_list = [
        {"tags": {"ns1": {"key1": ["val1"]}}},
        {"tags": {"ns2": {"key1": ["val1"]}}},
        {"tags": {"ns1": {"key1": ["val1"]}, "ns2": {"key1": ["val1"]}}},
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=ns1/key1=val1&tags=ns2/key1=val1")

    api_pagination_test(api_get, subtests, url, expected_total=1)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host_ids[2]


def test_get_no_host_with_different_tags_same_namespace(api_get):
    """
    Don't get a host with two tags in the same namespace, from which only one match. This is a
    regression test.
    """
    url = build_hosts_url(query="?tags=NS4/key1=val2&tags=NS1/key8=val1")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_get_host_with_tag_no_value_at_all(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no stored value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=no/key")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_with_tag_no_value_in_query(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with a stored value by a value-less query
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=NS1/key2")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_with_tag_no_namespace(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no namespace.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]
    url = build_hosts_url(query="?tags=key4=val4")

    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])
    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_with_tag_only_key(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no namespace.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]
    url = build_hosts_url(query="?tags=key5")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_by_display_name_and_tag(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to get only the host with the specified key and
    the specified display name
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?tags=NS1/key1=val1&display_name=host1")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_by_display_name_and_tag_backwards(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to get only the host with the specified key and
    the specified display name, but the parameters are backwards
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]
    url = build_hosts_url(query="?display_name=host1&tags=NS1/key1=val1")

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"], strict=False):
        assert host.id == result["id"]


def test_get_host_by_tag_empty_namespace_key_with_slash(mq_create_or_update_host, api_get):
    """
    Find host with a tag having an empty namespace and a '/' in the key.
    Verifies that RHINENG-17558 is fixed and the host is found.
    """
    target_tag = {"namespace": None, "key": "my/key", "value": "myvalue"}
    other_tag = {"namespace": None, "key": "other/key", "value": "myvalue"}
    ns_tag = {"namespace": "myns", "key": "my/key", "value": "myvalue"}

    target_host = mq_create_or_update_host(minimal_host(tags=[target_tag]))
    mq_create_or_update_host(minimal_host(tags=[other_tag]))
    ns_host = mq_create_or_update_host(minimal_host(tags=[ns_tag]))

    # Test filtering with key and value: ?tags=/my/key=myvalue
    url = build_hosts_url(query="?tags=/my/key=myvalue")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == target_host.id

    # Test filtering with key only (no value): ?tags=/my/key
    url = build_hosts_url(query="?tags=/my/key")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == target_host.id

    # Test filtering with explicit null namespace: ?tags=null/my/key=myvalue
    url = build_hosts_url(query="?tags=null/my/key=myvalue")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == target_host.id

    # Test filtering with explicit null namespace, key only: ?tags=null/my/key
    url = build_hosts_url(query="?tags=null/my/key")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == target_host.id

    # Test filtering with non-empty namespace: ?tags=myns/my/key=myvalue
    url = build_hosts_url(query="?tags=myns/my/key=myvalue")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == ns_host.id


def test_get_host_by_tag_empty_namespace_multiple_slashes_in_key(mq_create_or_update_host, api_get):
    """
    Find host with a tag having an empty namespace and multiple '/' in the key.
    """
    multi_slash_tag = {"namespace": None, "key": "nested/path/to/key", "value": "deep_val"}
    target_host = mq_create_or_update_host(minimal_host(tags=[multi_slash_tag]))

    # Test filtering with key and value: ?tags=/nested/path/to/key=deep_val
    url = build_hosts_url(query="?tags=/nested/path/to/key=deep_val")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == target_host.id

    # Test filtering with key only: ?tags=/nested/path/to/key
    url = build_hosts_url(query="?tags=/nested/path/to/key")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == target_host.id


def test_get_host_with_slash_in_tag_value(api_get):
    """
    Attempt to find host with a "/" in the tag value.
    Expects 200 response (RHINENG-17554).
    """
    url = build_hosts_url(query="?tags=namespace/key=my/value")
    response_status, _ = api_get(url)

    assert response_status == 200


def test_get_host_with_slash_in_tag_value_no_namespace(api_get):
    """
    Attempt to find host with a "/" in the tag value without a namespace.
    Expects 200 response (RHINENG-17554).
    """
    url = build_hosts_url(query="?tags=key=my/value")
    response_status, _ = api_get(url)

    assert response_status == 200


def test_get_host_by_tag_with_slash_in_value(mq_create_or_update_host, api_get):
    """
    Verify filtering by a tag containing a "/" in its value correctly matches the host.
    """
    tags = [
        {"namespace": "NS1", "key": "key1", "value": "my/value"},
        {"namespace": "NS1", "key": "key2", "value": "other_value"},
    ]
    host = minimal_host(tags=tags)
    created_host = mq_create_or_update_host(host)

    url = build_hosts_url(query="?tags=NS1/key1=my/value")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == created_host.id


def test_get_host_by_mixed_identity_tags_and_or(db_create_host, api_get, subtests):
    """
    Verify mixed tag query: OR semantics for same identity, AND semantics across different identities.
    Query: (ns1/env=prod OR ns1/env=stage) AND (ns2/app=web)
    """
    tags_data_list = [
        {"tags": {"ns1": {"env": ["prod"]}, "ns2": {"app": ["web"]}}},  # matches (prod, web)
        {"tags": {"ns1": {"env": ["stage"]}, "ns2": {"app": ["web"]}}},  # matches (stage, web)
        {"tags": {"ns1": {"env": ["dev"]}, "ns2": {"app": ["web"]}}},  # no match (wrong env)
        {"tags": {"ns1": {"env": ["prod"]}, "ns2": {"app": ["db"]}}},  # no match (wrong app)
        {"tags": {"ns1": {"env": ["prod"]}}},  # no match (missing app)
        {"tags": {"ns2": {"app": ["web"]}}},  # no match (missing env)
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=ns1/env=prod&tags=ns1/env=stage&tags=ns2/app=web")

    api_pagination_test(api_get, subtests, url, expected_total=2)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    result_ids = {result["id"] for result in response_data["results"]}
    assert result_ids == {host_ids[0], host_ids[1]}


def test_get_host_by_null_namespace_tags_uses_or(db_create_host, api_get, subtests):
    """
    Verify OR logic for tags with null/empty namespace sharing the same key.
    Query: (key1=val1 OR key1=val2)
    """
    tags_data_list = [
        {"tags": {"null": {"key1": ["val1"]}}},
        {"tags": {"null": {"key1": ["val2"]}}},
        {"tags": {"null": {"key1": ["val3"]}}},
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=key1=val1&tags=key1=val2")

    api_pagination_test(api_get, subtests, url, expected_total=2)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    result_ids = {result["id"] for result in response_data["results"]}
    assert result_ids == {host_ids[0], host_ids[1]}
