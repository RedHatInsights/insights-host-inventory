from itertools import chain

import pytest

from app.auth.identity import Identity
from lib.host_repository import find_hosts_by_staleness
from lib.host_repository import single_canonical_fact_host_query
from tests.helpers.api_utils import api_base_pagination_test
from tests.helpers.api_utils import api_pagination_invalid_parameters_test
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import api_query_test
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_host_ids_in_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_expected_host_list
from tests.helpers.api_utils import build_host_id_list_for_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_order_query_parameters
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
from tests.helpers.api_utils import UUID_1
from tests.helpers.api_utils import UUID_2
from tests.helpers.api_utils import UUID_3
from tests.helpers.db_utils import serialize_db_host
from tests.helpers.db_utils import update_host_in_db
from tests.helpers.graphql_utils import XJOIN_HOSTS_RESPONSE
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import SATELLITE_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


def test_query_all(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)

    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200
    assert expected_host_list == response_data["results"]

    api_base_pagination_test(api_get, subtests, HOST_URL, expected_total=len(created_hosts))


def test_query_using_display_name(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0]])

    url = build_hosts_url(query=f"?display_name={created_hosts[0].display_name}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert expected_host_list == response_data["results"]


def test_query_using_fqdn_two_results(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0], created_hosts[1]])

    url = build_hosts_url(query=f"?fqdn={created_hosts[0].fqdn}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    assert expected_host_list == response_data["results"]


def test_query_using_fqdn_one_result(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[2]])

    # Test upper- and lower-case values
    for fqdn in [created_hosts[2].fqdn.lower(), created_hosts[2].fqdn.upper()]:
        url = build_hosts_url(query=f"?fqdn={fqdn}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert len(response_data["results"]) == 1
        assert expected_host_list == response_data["results"]


def test_query_using_non_existent_fqdn(api_get):
    url = build_hosts_url(query="?fqdn=ROFLSAUCE.com")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_query_using_display_name_substring(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)

    host_name_substr = created_hosts[0].display_name[:4]

    url = build_hosts_url(query=f"?display_name={host_name_substr}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert expected_host_list == response_data["results"]

    api_pagination_test(api_get, subtests, url, expected_total=len(created_hosts))


def test_query_existent_hosts(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    host_lists = [created_hosts[0:1], created_hosts[1:3], created_hosts]

    for host_list in host_lists:
        with subtests.test(host_list=host_list):
            url = build_hosts_url(host_list_or_id=host_list)
            api_query_test(api_get, subtests, url, host_list)


def test_query_single_non_existent_host(api_get, subtests):
    url = build_hosts_url(host_list_or_id=generate_uuid())
    api_query_test(api_get, subtests, url, [])


def test_query_multiple_hosts_with_some_non_existent(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    host_list = created_hosts[0:1]

    existent_host_id_list = build_host_id_list_for_url(host_list)
    non_existent_host_id = generate_uuid()

    url = build_hosts_url(host_list_or_id=f"{non_existent_host_id},{existent_host_id_list}")
    api_query_test(api_get, subtests, url, host_list)


def test_query_invalid_host_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    bad_id_list = ["notauuid", "1234blahblahinvalid"]
    only_bad_id = bad_id_list.copy()

    # Can’t have empty string as an only ID, that results in 404 Not Found.
    more_bad_id_list = bad_id_list + [""]
    valid_id = created_hosts[0].id
    with_bad_id = [f"{valid_id},{bad_id}" for bad_id in more_bad_id_list]

    for host_id_list in chain(only_bad_id, with_bad_id):
        with subtests.test(host_id_list=host_id_list):
            url = build_hosts_url(host_list_or_id=host_id_list)
            response_status, response_data = api_get(url)
            assert response_status == 400


def test_query_host_id_with_incorrect_formats(api_get, subtests):
    host_id = "6a2f41a3-c54c-fce8-32d2-0324e1c32e22"

    bad_host_ids = (f" {host_id}", f"{{{host_id}", f"{host_id}-")

    for bad_host_id in bad_host_ids:
        with subtests.test():
            url = build_hosts_url(host_list_or_id=bad_host_id)
            response_status, response_data = api_get(url)
            assert response_status == 400


def test_query_with_branch_id_parameter(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    # branch_id parameter is accepted, but doesn’t affect results.
    url = build_hosts_url(host_list_or_id=created_hosts, query="?branch_id=123")
    api_query_test(api_get, subtests, url, created_hosts)


def test_query_invalid_paging_parameters(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(host_list_or_id=created_hosts)

    api_pagination_invalid_parameters_test(api_get, subtests, url)


def test_query_using_display_name_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].display_name}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2

    api_pagination_test(api_get, subtests, url, expected_total=2)


def test_query_using_fqdn_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[2].display_name}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1

    api_pagination_test(api_get, subtests, url, expected_total=1)


def test_query_using_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1

    api_pagination_test(api_get, subtests, url, expected_total=1)


def test_query_using_non_existent_hostname(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query="?hostname_or_id=NotGonnaFindMe")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0

    api_pagination_test(api_get, subtests, url, expected_total=0)


def test_query_using_non_existent_id(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query=f"?hostname_or_id={generate_uuid()}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0

    api_pagination_test(api_get, subtests, url, expected_total=0)


def test_query_with_matching_insights_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    # Test upper- and lower-case values
    for insights_id in [created_hosts[0].insights_id.upper(), created_hosts[0].insights_id.lower()]:
        url = build_hosts_url(query=f"?insights_id={insights_id}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert len(response_data["results"]) == 1

        api_pagination_test(api_get, subtests, url, expected_total=1)


def test_query_with_no_matching_insights_id(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query=f"?insights_id={generate_uuid()}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0

    api_pagination_test(api_get, subtests, url, expected_total=0)


def test_query_with_invalid_insights_id(mq_create_three_specific_hosts, api_get, subtests):
    url = build_hosts_url(query="?insights_id=notauuid")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_query_with_matching_insights_id_and_branch_id(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    valid_insights_id = created_hosts[0].insights_id

    url = build_hosts_url(query=f"?insights_id={valid_insights_id}&branch_id=123")
    response_status, response_data = api_get(url)

    assert response_status == 200


def test_query_using_fqdn_not_subset_match(mocker, api_get):
    mock = mocker.patch("api.host_query_db.single_canonical_fact_host_query", wraps=single_canonical_fact_host_query)
    fqdn = "some fqdn"
    url = build_hosts_url(query=f"?fqdn={fqdn}")
    api_get(url)
    mock.assert_called_once_with(Identity(USER_IDENTITY), "fqdn", fqdn)


def test_query_using_insights_id_not_subset_match(mocker, api_get):
    mock = mocker.patch("api.host_query_db.single_canonical_fact_host_query", wraps=single_canonical_fact_host_query)

    insights_id = "ff13a346-19cb-42ae-9631-44c42927fb92"

    url = build_hosts_url(query=f"?insights_id={insights_id}")
    api_get(url)

    mock.assert_called_once_with(Identity(USER_IDENTITY), "insights_id", insights_id)


def test_get_host_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]

    url = build_hosts_url(query="?tags=SPECIAL/tag=ToFind")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_multiple_hosts_by_tag(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0], created_hosts[1]]

    url = build_hosts_url(query="?tags=NS1/key1=val1&order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_by_multiple_tags(mq_create_three_specific_hosts, api_get, subtests):
    """
    Get only the host with all three tags on it and not the other host
    which both have some, but not all of the tags we query for.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[1]]

    url = build_hosts_url(query="?tags=NS1/key1=val1,NS2/key2=val2,NS3/key3=val3")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_by_subset_of_tags(mq_create_three_specific_hosts, api_get, subtests):
    """
    Get a host using a subset of it's tags
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[1]]

    url = build_hosts_url(query="?tags=NS1/key1=val1,NS3/key3=val3")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_with_different_tags_same_namespace(mq_create_three_specific_hosts, api_get, subtests):
    """
    get a host with two tags in the same namespace with diffent key and same value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]

    url = build_hosts_url(query="?tags=NS1/key1=val1,NS1/key2=val1")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_no_host_with_different_tags_same_namespace(mq_create_three_specific_hosts, api_get, subtests):
    """
    Don’t get a host with two tags in the same namespace, from which only one match. This is a
    regression test.
    """
    url = build_hosts_url(query="?tags=NS1/key1=val2,NS1/key2=val1")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 0


def test_get_host_with_same_tags_different_namespaces(mq_create_three_specific_hosts, api_get, subtests):
    """
    get a host with two tags in the same namespace with different key and same value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]

    url = build_hosts_url(query="?tags=NS3/key3=val3,NS1/key3=val3")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_with_tag_no_value_at_all(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no stored value
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]

    url = build_hosts_url(query="?tags=no/key")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_with_tag_no_value_in_query(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with a stored value by a value-less query
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]

    url = build_hosts_url(query="?tags=NS1/key2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


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

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_with_tag_only_key(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to find host with a tag with no namespace.
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[2]]

    url = build_hosts_url(query="?tags=key5")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_with_invalid_tag_no_key(mq_create_three_specific_hosts, api_get):
    """
    Attempt to find host with an incomplete tag (no key).
    Expects 400 response.
    """
    url = build_hosts_url(query="?tags=namespace/=Value")
    response_status, response_data = api_get(url)

    assert response_status == 400


def test_get_host_by_display_name_and_tag(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to get only the host with the specified key and
    the specified display name
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]

    url = build_hosts_url(query="?tags=NS1/key1=val1&display_name=host1")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


def test_get_host_by_display_name_and_tag_backwards(mq_create_three_specific_hosts, api_get, subtests):
    """
    Attempt to get only the host with the specified key and
    the specified display name, but the parameters are backwards
    """
    created_hosts = mq_create_three_specific_hosts
    expected_response_list = [created_hosts[0]]

    url = build_hosts_url(query="?display_name=host1&tags=NS1/key1=val1")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(expected_response_list) == len(response_data["results"])

    for host, result in zip(expected_response_list, response_data["results"]):
        assert host.id == result["id"]

    api_pagination_test(api_get, subtests, url, expected_total=len(expected_response_list))


@pytest.mark.parametrize(
    "tag_query,part_name",
    (
        (f"{'a' * 256}/key=val", "namespace"),
        (f"namespace/{'a' * 256}=val", "key"),
        (f"namespace/key={'a' * 256}", "value"),
    ),
)
def test_get_host_tag_part_too_long(tag_query, part_name, mq_create_three_specific_hosts, api_get):
    """
    send a request to find hosts with a string tag where the length
    of the namespace excedes the 255 character limit
    """

    url = build_hosts_url(query=f"?tags={tag_query}")
    response_status, response_data = api_get(url)

    assert_error_response(
        response_data, expected_status=400, expected_detail=f"{part_name} is longer than 255 characters"
    )


@pytest.mark.parametrize("tag_query", (";?:@&+$/-_.!~*'()'=#", " \t\n\r\f\v/ \t\n\r\f\v= \t\n\r\f\v"))
def test_get_host_with_unescaped_special_characters(tag_query, mq_create_or_update_host, api_get, subtests):
    tags = [
        {"namespace": ";?:@&+$", "key": "-_.!~*'()'", "value": "#"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(tags=tags)
    created_host = mq_create_or_update_host(host)

    url = build_hosts_url(query=f"?tags={quote(tag_query)}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"]
    assert response_data["results"][0]["id"] == created_host.id


@pytest.mark.parametrize(
    "namespace,key,value", ((";,/?:@&=+$", "-_.!~*'()", "#"), (" \t\n\r\f\v", " \t\n\r\f\v", " \t\n\r\f\v"))
)
def test_get_host_with_escaped_special_characters(namespace, key, value, mq_create_or_update_host, api_get):
    tags = [
        {"namespace": ";,/?:@&=+$", "key": "-_.!~*'()", "value": "#"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

    host = minimal_host(tags=tags)
    created_host = mq_create_or_update_host(host)

    tags_query = quote(f"{quote_everything(namespace)}/{quote_everything(key)}={quote_everything(value)}")
    url = build_hosts_url(query=f"?tags={tags_query}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"]
    assert response_data["results"][0]["id"] == created_host.id


def tests_hosts_are_ordered_by_updated_desc_by_default(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    created_hosts.reverse()

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=created_hosts)


def tests_hosts_ordered_by_updated_are_descending_by_default(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    created_hosts.reverse()

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    order_query_parameters = build_order_query_parameters(order_by="updated")

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=created_hosts)


def tests_hosts_are_ordered_by_updated_descending(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    created_hosts.reverse()

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    order_query_parameters = build_order_query_parameters(order_by="updated", order_how="DESC")

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=created_hosts)


def tests_hosts_are_ordered_by_updated_ascending(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    order_query_parameters = build_order_query_parameters(order_by="updated", order_how="ASC")

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=created_hosts)


def tests_hosts_ordered_by_display_name_are_ascending_by_default(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    expected_hosts = [created_hosts[3], created_hosts[0], created_hosts[1], created_hosts[2]]

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    order_query_parameters = build_order_query_parameters(order_by="display_name")

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=expected_hosts)


def tests_hosts_are_ordered_by_display_name_ascending(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    expected_hosts = [created_hosts[3], created_hosts[0], created_hosts[1], created_hosts[2]]

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    order_query_parameters = build_order_query_parameters(order_by="display_name", order_how="ASC")

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=expected_hosts)


def tests_hosts_are_ordered_by_display_name_descending(mq_create_four_specific_hosts, api_get, subtests):
    created_hosts = mq_create_four_specific_hosts
    expected_hosts = [created_hosts[2], created_hosts[1], created_hosts[3], created_hosts[0]]

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    order_query_parameters = build_order_query_parameters(order_by="display_name", order_how="DESC")

    for url in urls:
        with subtests.test(url=url):
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert_response_status(response_status, expected_status=200)
            assert_host_ids_in_response(response_data, expected_hosts=expected_hosts)


def _test_order_by_id_desc(inventory_config, api_get, subtests, created_hosts, specifications, order_by, order_how):
    for updates, expected_added_hosts in specifications:
        # Update hosts to they have a same modified_on timestamp, but different IDs.
        # New modified_on value must be set explicitly so it’s saved the same to all
        # records. Otherwise SQLAlchemy would consider it unchanged and update it
        # automatically to its own "now" only for records whose ID changed.
        new_modified_on = now()

        for added_host_index, new_id in updates:
            host = update_host_in_db(created_hosts[added_host_index].id, id=new_id, modified_on=new_modified_on)
            created_hosts[added_host_index] = serialize_db_host(host, inventory_config)

        # Check the order in the response against the expected order. Only indexes
        # are passed, because self.added_hosts values were replaced during the
        # update.
        expected_hosts = tuple(created_hosts[added_host_index] for added_host_index in expected_added_hosts)

        urls = (HOST_URL, build_hosts_url(created_hosts), build_system_profile_url(created_hosts))
        for url in urls:
            with subtests.test(url=url, updates=updates):
                order_query_parameters = build_order_query_parameters(order_by=order_by, order_how=order_how)
                response_status, response_data = api_get(url, query_parameters=order_query_parameters)

                assert_response_status(response_status, expected_status=200)
                assert_host_ids_in_response(response_data, expected_hosts)


def test_hosts_ordered_by_updated_are_also_ordered_by_id_desc(
    inventory_config, api_get, mq_create_four_specific_hosts, subtests
):
    created_hosts = mq_create_four_specific_hosts

    # The first two hosts (0 and 1) with different display_names will have the same
    # modified_on timestamp, but different IDs.
    specifications = (
        (((0, UUID_1), (1, UUID_2)), (1, 0, 3, 2)),
        (((1, UUID_2), (0, UUID_3)), (0, 1, 3, 2)),
        # UPDATE order may influence actual result order.
        (((1, UUID_2), (0, UUID_1)), (1, 0, 3, 2)),
        (((0, UUID_3), (1, UUID_2)), (0, 1, 3, 2)),
    )

    _test_order_by_id_desc(
        inventory_config, api_get, subtests, created_hosts, specifications, order_by="updated", order_how="DESC"
    )


def test_hosts_ordered_by_display_name_are_also_ordered_by_id_desc(
    inventory_config, api_get, mq_create_four_specific_hosts, subtests
):
    created_hosts = mq_create_four_specific_hosts

    # The two hosts with the same display_name (1 and 2) will have the same
    # modified_on timestamp, but different IDs.
    specifications = (
        (((0, UUID_1), (3, UUID_2)), (3, 0, 1, 2)),
        (((3, UUID_2), (0, UUID_3)), (0, 3, 1, 2)),
        # UPDATE order may influence actual result order.
        (((3, UUID_2), (0, UUID_1)), (3, 0, 1, 2)),
        (((0, UUID_3), (3, UUID_2)), (0, 3, 1, 2)),
    )
    _test_order_by_id_desc(
        inventory_config, api_get, subtests, created_hosts, specifications, order_by="display_name", order_how="ASC"
    )


def test_invalid_order_by(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    for url in urls:
        with subtests.test(url=url):
            order_query_parameters = build_order_query_parameters(order_by="fqdn", order_how="ASC")
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


def test_invalid_order_how(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    for url in urls:
        with subtests.test(url=url):
            order_query_parameters = build_order_query_parameters(order_by="display_name", order_how="asc")
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


def test_only_order_how(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts

    urls = (
        HOST_URL,
        build_hosts_url(host_list_or_id=created_hosts),
        build_system_profile_url(host_list_or_id=created_hosts),
    )
    for url in urls:
        with subtests.test(url=url):
            order_query_parameters = build_order_query_parameters(order_by=None, order_how="ASC")
            response_status, response_data = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


def test_get_hosts_only_insights(mq_create_three_specific_hosts, mq_create_or_update_host, api_get):
    created_hosts_with_insights_id = mq_create_three_specific_hosts

    host_without_insights_id = minimal_host(subscription_manager_id=generate_uuid(), fqdn="different.fqdn.com")
    created_host_without_insights_id = mq_create_or_update_host(host_without_insights_id)

    url = build_hosts_url(query="?registered_with=insights")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 3

    result_ids = sorted([host["id"] for host in response_data["results"]])
    expected_ids = sorted([host.id for host in created_hosts_with_insights_id])
    non_expected_id = created_host_without_insights_id.id

    assert expected_ids == result_ids
    assert non_expected_id not in expected_ids


def test_get_hosts_with_RBAC_allowed(subtests, mocker, db_create_host, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)


def test_get_hosts_with_RBAC_denied(subtests, mocker, db_create_host, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_hosts_by_staleness_mock = mocker.patch(
        "lib.host_repository.find_hosts_by_staleness", wraps=find_hosts_by_staleness
    )

    for response_file in READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 403)

            find_hosts_by_staleness_mock.assert_not_called()


def test_get_hosts_with_RBAC_bypassed_as_system(db_create_host, api_get, enable_rbac):
    host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": generate_uuid()}})

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


def test_get_hosts_sap_system(patch_xjoin_post, api_get, subtests, query_source_xjoin):
    patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 1}, "data": []}}})

    values = ("true", "false", "nil", "not_nil")

    for value in values:
        with subtests.test(value=value):
            implicit_url = build_hosts_url(query=f"?filter[system_profile][sap_system]={value}")
            eq_url = build_hosts_url(query=f"?filter[system_profile][sap_system][eq]={value}")

            implicit_response_status, implicit_response_data = api_get(implicit_url)
            eq_response_status, eq_response_data = api_get(eq_url)

            assert_response_status(implicit_response_status, 200)
            assert_response_status(eq_response_status, 200)
            assert implicit_response_data["total"] == 1
            assert eq_response_data["total"] == 1


def test_get_hosts_sap_sids(patch_xjoin_post, api_get, subtests, query_source_xjoin):
    patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 1}, "data": []}}})

    filter_paths = ("[system_profile][sap_sids][]", "[system_profile][sap_sids][contains][]")
    value_sets = (("ABC",), ("BEN", "A72"), ("CDA", "MK2", "C2C"))

    for path in filter_paths:
        for values in value_sets:
            with subtests.test(values=values, path=path):
                url = build_hosts_url(query="?" + "".join([f"filter{path}={value}&" for value in values]))

                response_status, response_data = api_get(url)

                assert_response_status(response_status, 200)
                assert response_data["total"] == 1


def test_get_hosts_with_satellite_identity(db_create_host, api_get):
    owner_id = SATELLITE_IDENTITY["system"]["cn"]
    host_one = db_create_host(SATELLITE_IDENTITY, extra_data={"system_profile_facts": {"owner_id": owner_id}})
    host_two = db_create_host(SATELLITE_IDENTITY, extra_data={"system_profile_facts": {"owner_id": owner_id}})

    host_ids = [str(host_one.id), str(host_two.id)]
    response_status, response_data = api_get(HOST_URL, identity=SATELLITE_IDENTITY)

    # check both hosts gets fetched when using satellite identity
    assert_response_status(response_status, 200)
    assert response_data["total"] == 2
    for host_data in response_data["results"]:
        assert host_data["id"] in host_ids

    url = build_system_profile_url(host_list_or_id=[host_one, host_two])
    response_status, response_data = api_get(url, identity=SATELLITE_IDENTITY)

    # check the owner_id is identical for both hosts
    assert_response_status(response_status, 200)
    for host_data in response_data["results"]:
        assert host_data["system_profile"]["owner_id"] == owner_id


def test_get_hosts_sap_system_bad_parameter_values(patch_xjoin_post, api_get, subtests, query_source_xjoin):
    patch_xjoin_post(response={})

    values = "Garfield"

    for value in values:
        with subtests.test(value=value):
            implicit_url = build_hosts_url(query=f"?filter[system_profile][sap_system]={value}")
            eq_url = build_hosts_url(query=f"?filter[system_profile][sap_system][eq]={value}")

            implicit_response_status, implicit_response_data = api_get(implicit_url)
            eq_response_status, eq_response_data = api_get(eq_url)

            assert_response_status(implicit_response_status, 400)
            assert_response_status(eq_response_status, 400)


def test_get_hosts_unsupported_filter(patch_xjoin_post, api_get, query_source_xjoin):
    patch_xjoin_post(response={})

    implicit_url = build_hosts_url(query="?filter[system_profile][bad_thing]=Banana")
    eq_url = build_hosts_url(query="?filter[Bad_thing][Extra_bad_one][eq]=Pinapple")

    implicit_response_status, implicit_response_data = api_get(implicit_url)
    eq_response_status, eq_response_data = api_get(eq_url)

    assert_response_status(implicit_response_status, 400)
    assert_response_status(eq_response_status, 400)


def test_sp_sparse_fields_xjoin_response_translation(patch_xjoin_post, query_source_xjoin, api_get):
    host_one_id, host_two_id = generate_uuid(), generate_uuid()

    hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

    for query, xjoin_post in (
        (
            "?fields[system_profile]=os_kernel_version,arch,sap_sids",
            [
                {
                    "id": host_one_id,
                    "system_profile_facts": {
                        "os_kernel_version": "3.10.0",
                        "arch": "string",
                        "sap_sids": ["H2O", "PH3", "CO2"],
                    },
                },
                {"id": host_two_id, "system_profile_facts": {"os_kernel_version": "1.11.1", "arch": "host_arch"}},
            ],
        ),
        (
            "?fields[system_profile]=unknown_field",
            [{"id": host_one_id, "system_profile_facts": {}}, {"id": host_two_id, "system_profile_facts": {}}],
        ),
        (
            "?fields[system_profile]=os_kernel_version,arch&fields[system_profile]=sap_sids",
            [
                {
                    "id": host_one_id,
                    "system_profile_facts": {
                        "os_kernel_version": "3.10.0",
                        "arch": "string",
                        "sap_sids": ["H2O", "PH3", "CO2"],
                    },
                },
                {"id": host_two_id, "system_profile_facts": {"os_kernel_version": "1.11.1", "arch": "host_arch"}},
            ],
        ),
    ):
        patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 2, "count": 2}, "data": xjoin_post}}})
        response_status, response_data = api_get(build_system_profile_url(hosts, query=query))

        assert_response_status(response_status, 200)
        assert response_data["total"] == 2
        assert response_data["count"] == 2
        assert response_data["results"][0]["system_profile"] == xjoin_post[0]["system_profile_facts"]


def test_sp_sparse_fields_xjoin_response_with_invalid_field(
    patch_xjoin_post, query_source_xjoin, db_create_host, api_get
):
    host = minimal_host(id=generate_uuid())

    xjoin_post = [
        {
            "id": str(host.id),
            "invalid_key": {"os_kernel_version": "3.10.0", "arch": "string", "sap_sids": ["H2O", "PH3", "CO2"]},
        }
    ]
    patch_xjoin_post(response={"data": {"hosts": {"meta": {"total": 1, "count": 1}, "data": xjoin_post}}})
    response_status, response_data = api_get(
        build_system_profile_url([host], query="?fields[system_profile]=os_kernel_version,arch,sap_sids")
    )

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["count"] == 1
    assert response_data["results"][0]["system_profile"] == {}


def test_validate_sp_sparse_fields_invalid_requests(query_source_xjoin, api_get):
    for query in (
        "?fields[system_profile]=os_kernel_version&order_how=ASC",
        "?fields[system_profile]=os_kernel_version&order_by=modified",
        "?fields[system_profile]=os_kernel_version&order_how=display_name&order_by=NOO",
        "?fields[foo]=bar",
    ):
        host_one_id, host_two_id = generate_uuid(), generate_uuid()
        hosts = [minimal_host(id=host_one_id), minimal_host(id=host_two_id)]

        response_status, response_data = api_get(build_system_profile_url(hosts, query=query))
        assert response_status == 400


def test_host_list_sp_fields_requested(patch_xjoin_post, query_source_xjoin, api_get):
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE})
    fields = ["test_data", "random"]
    response_status, response_data = api_get(HOST_URL + f"?fields[system_profile]={','.join(fields)}")

    assert response_status == 200

    for host_data in response_data["results"]:
        assert "system_profile" in host_data
        for key in host_data["system_profile"].keys():
            assert key in fields


def test_host_list_sp_fields_not_requested(patch_xjoin_post, query_source_xjoin, api_get):
    patch_xjoin_post(response={"data": XJOIN_HOSTS_RESPONSE})
    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200

    for host_data in response_data["results"]:
        assert "system_profile" not in host_data


def test_unindexed_fields_fail_gracefully(query_source_xjoin, api_get):
    url_builders = (
        build_hosts_url,
        build_system_profile_sap_sids_url,
        build_tags_url,
        build_system_profile_sap_system_url,
    )

    for url_builder in url_builders:
        for query in ("?filter[system_profile][installed_packages_delta]=foo",):
            response_status, _ = api_get(url_builder(query=query))
            assert response_status == 400


# This test verifies that the [contains] operation is accepted for a string array field such as cpu_flags
def test_get_hosts_contains_works_on_string_array(patch_xjoin_post, api_get, subtests, query_source_xjoin):
    url_builders = (
        build_hosts_url,
        build_system_profile_sap_sids_url,
        build_tags_url,
        build_system_profile_sap_system_url,
    )

    for url_builder in url_builders:
        for query in ("?filter[system_profile][cpu_flags][contains]=ex1",):
            response_status, _ = api_get(url_builder(query=query))
            assert response_status == 200


# This test verifies that the [contains] operation is denied for a non-array string field such as cpu_model
def test_get_hosts_contains_invalid_on_string_not_array(patch_xjoin_post, api_get, subtests, query_source_xjoin):
    url_builders = (
        build_hosts_url,
        build_system_profile_sap_sids_url,
        build_tags_url,
        build_system_profile_sap_system_url,
    )

    for url_builder in url_builders:
        for query in ("?filter[system_profile][cpu_model][contains]=Intel(R) I7(R) CPU I7-10900k 0 @ 4.90GHz",):
            response_status, _ = api_get(url_builder(query=query))
            assert response_status == 400
