import logging
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from itertools import combinations
from typing import Any
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture
from pytest_subtests import SubTests

from api.filtering.filtering_common import escape_ilike_value
from app.models.host import Host
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import LEGACY_HOST_URL
from tests.helpers.api_utils import api_base_pagination_test
from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import assert_host_lists_equal
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_expected_host_list
from tests.helpers.api_utils import build_host_exists_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_order_query_parameters
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import create_hosts_by_reporter_and_staleness
from tests.helpers.api_utils import quote
from tests.helpers.api_utils import quote_everything
from tests.helpers.test_utils import IDENTITY_WITHOUT_HOSTS
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now

logger = logging.getLogger(__name__)


def test_get_host_with_slash_in_key_name(api_get):
    """
    Attempt to find host with a "/" in the key.
    Expects 200 response.
    """
    url = build_hosts_url(query="?tags=namespace/key/key_value=Value")
    response_status, _ = api_get(url)

    assert response_status == 200


def test_get_host_with_slash_in_key_name_empty_namespace(api_get):
    """
    Attempt to find host with a "/" in the key with an empty namespace.
    Expects 200 response.
    """
    url = build_hosts_url(query="?tags=/key/key_value=Value")
    response_status, _ = api_get(url)

    assert response_status == 200


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
            response_status, _ = api_get(url, query_parameters=order_query_parameters)
            assert response_status == 400


@pytest.mark.parametrize(
    "value",
    ("insights", "cloud-connector", "puptoo", "rhsm-conduit", "yupana", "puptoo&registered_with=yupana"),
)
def test_get_hosts_registered_with(api_get, value):
    url = build_hosts_url(query=f"?registered_with={value}")
    response_status, _ = api_get(url)

    assert response_status == 200


def test_query_variables_registered_with_using_unknown_reporter(api_get):
    MSG = "'unknown' is not one of ["
    url = build_hosts_url(query="?registered_with=unknown")

    response_status, response_data = api_get(url)

    assert response_status == 400
    assert MSG in str(response_data)


@pytest.mark.parametrize(
    "query, extra_param",
    (
        ("?id=11111111-1111-1111-1111-111111111111", "id"),
        ("?foo=bar", "foo"),
        ("?not_a_param=1", "not_a_param"),
    ),
)
def test_get_hosts_rejects_undeclared_query_parameters(api_get, query, extra_param):
    response_status, response_data = api_get(build_hosts_url(query=query))

    assert response_status == 400
    assert response_data["detail"] == f"Extra query parameter(s) {extra_param} not in spec"


@pytest.mark.parametrize(
    "host_url",
    (HOST_URL, LEGACY_HOST_URL),
)
def test_query_all(mq_create_three_specific_hosts, api_get, subtests, host_url):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)

    response_status, response_data = api_get(host_url)
    api_base_pagination_test(api_get, subtests, host_url, expected_total=len(expected_host_list))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


@pytest.mark.parametrize("branch_id", ("", "54b80cb3-7fca-4444-9faf-aa43e8a560c3"))
def test_query_all_ignores_branch_id(mq_create_three_specific_hosts, api_get, branch_id):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)

    url = build_hosts_url(query=f"?branch_id={branch_id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_all_with_edge(mq_create_three_specific_hosts, mq_create_edge_host, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts + [mq_create_edge_host]
    expected_host_list = build_expected_host_list(created_hosts)

    response_status, response_data = api_get(HOST_URL)
    api_base_pagination_test(api_get, subtests, HOST_URL, expected_total=len(expected_host_list))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])


@pytest.mark.parametrize(
    "query",
    (
        (f"fqdn={generate_uuid()}&display_name={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"hostname_or_id={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&fqdn={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&fqdn={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (
            f"display_name={generate_uuid()}&fqdn={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"
        ),
    ),
)
def test_query_by_conflitcting_ids(api_get, query):
    # Not allowed to query on more than one of these fields at once
    url = build_hosts_url(query=f"?{query}")
    response_status, response_body = api_get(url)

    assert response_status == 400
    assert (
        "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        in response_body["detail"]
    )


@pytest.mark.parametrize(
    "param_name,value_getter",
    [
        ("hostname_or_id", lambda h: h[0].id),
        ("insights_id", lambda h: h[0].insights_id.upper()),
        ("subscription_manager_id", lambda h: h[0].subscription_manager_id),
    ],
)
def test_query_using_single_field(mq_create_three_specific_hosts, api_get, subtests, param_name, value_getter):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?{param_name}={value_getter(created_hosts)}")
    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)
    assert response_status == 200
    assert len(response_data["results"]) == 1


@pytest.mark.parametrize("tag_query", (";?:@&+$/-_.!~*'()'=#", " \t\n\r\f\v/ \t\n\r\f\v= \t\n\r\f\v"))
def test_get_host_with_unescaped_special_characters(tag_query, mq_create_or_update_host, api_get):
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


def test_query_hosts_filter_updated_start_end(mq_create_or_update_host, api_get):
    host_list = [mq_create_or_update_host(minimal_host(insights_id=generate_uuid())) for _ in range(3)]

    url = build_hosts_url(query=f"?updated_start={host_list[0].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # This query should return all 3 hosts
    assert len(response_data["results"]) == 3

    url = build_hosts_url(query=f"?updated_end={host_list[0].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # This query should return only the first host
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["insights_id"] == host_list[0].insights_id

    url = build_hosts_url(
        query=(
            f"?updated_start={host_list[0].updated.replace('+00:00', 'Z')}"
            f"&updated_end={host_list[1].updated.replace('+00:00', 'Z')}"
        )
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return 2 hosts
    assert len(response_data["results"]) == 2

    url = build_hosts_url(query=f"?updated_start={host_list[2].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return only the last host
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["insights_id"] == host_list[2].insights_id

    url = build_hosts_url(query=f"?updated_end={host_list[2].updated.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return all 3 hosts
    assert len(response_data["results"]) == 3


def test_query_hosts_filter_last_check_in_start_end(mq_create_or_update_host, api_get):
    host_list = [mq_create_or_update_host(minimal_host(insights_id=generate_uuid())) for _ in range(3)]

    url = build_hosts_url(query=f"?last_check_in_start={host_list[0].last_check_in.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # This query should return all 3 hosts
    assert len(response_data["results"]) == 3

    url = build_hosts_url(query=f"?last_check_in_end={host_list[0].last_check_in.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # This query should return only the first host
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["insights_id"] == host_list[0].insights_id

    url = build_hosts_url(
        query=(
            f"?last_check_in_start={host_list[0].last_check_in.replace('+00:00', 'Z')}"
            f"&last_check_in_end={host_list[1].last_check_in.replace('+00:00', 'Z')}"
        )
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return 2 hosts
    assert len(response_data["results"]) == 2

    url = build_hosts_url(query=f"?last_check_in_start={host_list[2].last_check_in.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return only the last host
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["insights_id"] == host_list[2].insights_id

    url = build_hosts_url(query=f"?last_check_in_end={host_list[2].last_check_in.replace('+00:00', 'Z')}")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # This query should return all 3 hosts
    assert len(response_data["results"]) == 3


def test_query_hosts_filter_last_check_in_both_same(mq_create_or_update_host, api_get):
    match_host = mq_create_or_update_host(minimal_host())
    nomatch_host = mq_create_or_update_host(minimal_host())
    url = build_hosts_url(
        query=(
            f"?last_check_in_start={match_host.last_check_in.replace('+00:00', 'Z')}"
            f"&last_check_in_end={match_host.last_check_in.replace('+00:00', 'Z')}"
        )
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == match_host.id
    assert response_data["results"][0]["id"] != nomatch_host.id


@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_query_hosts_filter_updated_last_check_in_start_after_end(api_get, param_prefix):
    url = build_hosts_url(
        query=f"?{param_prefix}_start={datetime.now()}&{param_prefix}_end={datetime.now() - timedelta(days=1)}"
    )
    response_status, response_data = api_get(url)
    assert response_status == 400
    assert f"{param_prefix}_start cannot be after {param_prefix}_end." in response_data["detail"]


@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_get_hosts_order_by_last_check_in(db_create_host, api_get, order_how):
    host0 = str(db_create_host().id)
    host1 = str(db_create_host().id)

    url = build_hosts_url(query=f"?order_by=last_check_in&order_how={order_how}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    hosts = response_data["results"]
    if order_how == "DESC":
        assert host1 == hosts[0]["id"]
        assert host0 == hosts[1]["id"]
    else:
        assert host0 == hosts[0]["id"]
        assert host1 == hosts[1]["id"]


@pytest.mark.parametrize("num_hosts_to_query", (1, 3))
@pytest.mark.parametrize("order_by", ("updated", "display_name", "group_name", "operating_system", "last_check_in"))
@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_query_using_id_list(
    mq_create_three_specific_hosts, api_get, subtests, num_hosts_to_query, order_by, order_how
):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(
        host_list_or_id=[host.id for host in created_hosts[:num_hosts_to_query]],
        query=f"?order_by={order_by}&order_how={order_how}",
    )

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=num_hosts_to_query)

    assert response_status == 200
    assert len(response_data["results"]) == num_hosts_to_query


def test_query_using_id_list_nonexistent_host(api_get):
    response_status, _ = api_get(build_hosts_url(generate_uuid()))
    assert response_status == 404


@pytest.mark.parametrize("legacy_field", ("crowdstrike", "ibm_db2", "oracle_db"))
@pytest.mark.parametrize("endpoint", ("list", "by_id", "system_profile"))
def test_sparse_legacy_workload_root_fields_omitted(db_create_host, api_get, legacy_field, endpoint):
    host = db_create_host(extra_data={"system_profile_facts": {"arch": "x86_64", "host_type": "edge"}})
    query = f"?fields[system_profile]={legacy_field}"
    if endpoint == "list":
        url = build_hosts_url(query=query)
    elif endpoint == "by_id":
        url = build_hosts_url(host_list_or_id=host.id, query=query)
    else:
        url = build_system_profile_url(host.id, query=query)

    response_status, response_data = api_get(url)

    assert response_status == 200
    for result in response_data["results"]:
        assert legacy_field not in result.get("system_profile", {})


def test_query_all_sparse_fields(db_create_multiple_hosts, api_get):
    # Create hosts that have a system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    url = build_hosts_url(query="?fields[system_profile]=arch,host_type")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" in result["system_profile"]
        assert "host_type" in result["system_profile"]
        assert "os_kernel_version" not in result["system_profile"]
        assert "owner_id" not in result["system_profile"]


def test_query_sys_profile_with_sql_characters(db_create_multiple_hosts, api_get):
    # Create hosts that have a system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    url = build_hosts_url(query="?filter[system_profile][bios_vendor]=%3E/%3AX%26x5wVZCj%25mC")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" in result["system_profile"]
        assert "host_type" in result["system_profile"]
        assert "os_kernel_version" not in result["system_profile"]
        assert "owner_id" not in result["system_profile"]


def test_query_by_id_sparse_fields(db_create_multiple_hosts, api_get):
    # Create hosts that have a system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    created_hosts = db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    url = build_hosts_url(
        host_list_or_id=created_hosts[0].id, query="?fields[system_profile]=os_kernel_version,owner_id"
    )

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that the system_profile is not in the response by default
    for result in response_data["results"]:
        assert "system_profile" in result
        assert "arch" not in result["system_profile"]
        assert "host_type" not in result["system_profile"]
        assert "os_kernel_version" in result["system_profile"]
        assert "owner_id" in result["system_profile"]


def test_query_by_id_culled_hosts(db_create_host, api_get):
    # Create a culled host
    with patch("app.models.utils.datetime", **{"now.return_value": now() - timedelta(days=365)}):
        created_host_id = str(db_create_host().id)

    url = build_hosts_url(host_list_or_id=created_host_id)
    # The host should not be returned as it is in the "culled" state
    # Because the host is culled, the API should return a 404
    response_status, _ = api_get(url)
    assert response_status == 404


def test_query_by_registered_with(db_create_multiple_hosts, api_get, subtests):
    _now = now()
    registered_with_data = [
        {"puptoo": _now.isoformat(), "yupana": (_now - timedelta(days=3)).isoformat()},
        {
            "puptoo": (_now - timedelta(days=1)).isoformat(),
            "satellite": (_now - timedelta(days=3)).isoformat(),
        },
        {
            "puptoo": (_now - timedelta(days=30)).isoformat(),
            "discovery": (_now - timedelta(days=3)).isoformat(),
        },
        {"rhsm-conduit": (_now - timedelta(days=1)).isoformat()},
    ]
    insights_ids = [generate_uuid() for _ in range(len(registered_with_data))]

    # Create an association between the insights IDs
    registered_with_host_data = dict(zip(insights_ids, registered_with_data, strict=False))

    # Create hosts for the above host data
    _ = [
        db_create_multiple_hosts(
            how_many=1,
            extra_data={
                "insights_id": insights_id,
                "per_reporter_staleness": registered_with_host_data[insights_id],
            },
        )
        for insights_id in insights_ids
    ]

    expected_reporter_results_map = {
        "puptoo": 2,
        "yupana": 3,
        "!yupana": 1,
        "rhsm-conduit": 1,
        "rhsm-conduit&registered_with=yupana": 4,
    }
    for reporter, count in expected_reporter_results_map.items():
        with subtests.test():
            url = build_hosts_url(query=f"?registered_with={reporter}")
            # Validate the basics, i.e. response code and results size
            response_status, response_data = api_get(url)
            assert response_status == 200
            assert count == len(response_data["results"])


def test_get_hosts_filter_by_reporter_and_staleness(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
    mocker: MockerFixture,
    subtests: SubTests,
) -> None:
    reporters = ("puptoo", "yupana")
    states = ("fresh", "stale", "stale_warning")
    hosts = create_hosts_by_reporter_and_staleness(db_create_host, mocker, reporters=reporters)

    for state in states:
        for reporter in reporters:
            with subtests.test(state=state, reporter=reporter):
                url = build_hosts_url(query=f"?staleness={state}&registered_with={reporter}")
                response_status, response_data = api_get(url)
                assert response_status == 200

                expected_id = str(hosts[state][reporter].id)
                result_ids = {h["id"] for h in response_data["results"]}
                assert expected_id in result_ids

                unexpected_ids = {
                    str(hosts[s][r].id) for s in states for r in reporters if (s, r) != (state, reporter)
                }
                assert not result_ids & unexpected_ids


@pytest.mark.parametrize(
    "workload_sp_data,sp_filter_param",
    (
        # Satellite: only containers (containerized-only, no RPM fields)
        (
            {
                "workloads": {
                    "satellite": {
                        "containers": [
                            {"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}
                        ]
                    }
                }
            },
            "[workloads][satellite][is]=not_nil",
        ),
        # Satellite: only foremanctl_version
        (
            {"workloads": {"satellite": {"foremanctl_version": "3.0.0"}}},
            "[workloads][satellite][is]=not_nil",
        ),
        # Satellite: containers + foremanctl_version
        (
            {
                "workloads": {
                    "satellite": {
                        "foremanctl_version": "3.0.0",
                        "containers": [
                            {"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}
                        ],
                    }
                }
            },
            "[workloads][satellite][is]=not_nil",
        ),
        # Satellite: all fields (hybrid RPM + containerized)
        (
            {
                "workloads": {
                    "satellite": {
                        "type": "server",
                        "version": "6.17.6.1",
                        "foremanctl_version": "3.0.0",
                        "containers": [
                            {"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}
                        ],
                    }
                }
            },
            "[workloads][satellite][is]=not_nil",
        ),
        # Ansible: only containers (containerized-only)
        (
            {
                "workloads": {
                    "ansible": {
                        "containers": [
                            {"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}
                        ]
                    }
                }
            },
            "[workloads][ansible][is]=not_nil",
        ),
        # Ansible: containers + traditional version fields (hybrid)
        (
            {
                "workloads": {
                    "ansible": {
                        "controller_version": "1.0",
                        "containers": [
                            {"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}
                        ],
                    }
                }
            },
            "[workloads][ansible][is]=not_nil",
        ),
        # Ansible: only traditional version fields (RPM-based, regression check)
        (
            {"workloads": {"ansible": {"controller_version": "1.0", "receptor_version": "1.5.2"}}},
            "[workloads][ansible][is]=not_nil",
        ),
    ),
)
def test_workload_not_nil_filter_combinations(db_create_host, api_get, workload_sp_data, sp_filter_param):
    match_sp_data = {"system_profile_facts": workload_sp_data}
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    nomatch_sp_data = {"system_profile_facts": {"arch": "x86_64"}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "query_filter_param,match_host_facts",
    (
        ("?display_name=1*m", [{"display_name": "HkqL12lmIW"}]),
        (
            "?hostname_or_id=1*m",
            [
                {"display_name": "HkqL12lmIW"},
                {"fqdn": "HkqL1m2lIW", "subscription_manager_id": generate_uuid()},
            ],
        ),
    ),
)
def test_query_host_fuzzy_match(db_create_host, api_get, query_filter_param, match_host_facts):
    # Create host with matching data
    match_host_id_list = [str(db_create_host(extra_data=host_fact).id) for host_fact in match_host_facts]

    # Create host with differing SP
    nomatch_host_facts = [
        {"display_name": "masdf1"},
        {"fqdn": "masdf1", "subscription_manager_id": generate_uuid()},
    ]
    nomatch_host_id_list = [str(db_create_host(extra_data=host_fact).id) for host_fact in nomatch_host_facts]

    url = build_hosts_url(query=query_filter_param)

    response_status, response_data = api_get(url)

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert response_status == 200
    assert len(response_ids) == len(match_host_facts)

    for response_id in response_ids:
        assert response_id in match_host_id_list
        assert response_id not in nomatch_host_id_list


def test_query_hosts_multiple_os(api_get, db_create_host, subtests):
    sp_facts_list = [
        {"operating_system": {"name": "RHEL", "major": 7, "minor": 7}, "host_type": "edge"},
        {"operating_system": {"name": "RHEL", "major": 7, "minor": 8}, "host_type": "edge"},
        {"operating_system": {"name": "RHEL", "major": 7, "minor": 7}},
        {"operating_system": {"name": "RHEL", "major": 7, "minor": 8}},
        {"operating_system": {"name": "RHEL", "major": 7, "minor": 8}},
        {"operating_system": {"name": "RHEL", "major": 7, "minor": 10}},
        {"operating_system": {"name": "RHEL", "major": 8, "minor": 0}},
        {"operating_system": {"name": "RHEL", "major": 8, "minor": 5}},
        {"operating_system": {"name": "RHEL", "major": 9, "minor": 1}},
    ]

    for sp_facts in sp_facts_list:
        # Create the hosts we expect to be returned
        db_create_host(extra_data={"system_profile_facts": sp_facts})

        # Create hosts with the same data, but on a different account
        db_create_host(
            identity=SERVICE_ACCOUNT_IDENTITY,
            extra_data={
                "system_profile_facts": sp_facts,
            },
        )

    sp_filter_param_list = [
        ("[operating_system][RHEL][version]=7.7", 2),
        ("[operating_system][RHEL][version][]=7.7&filter[system_profile][operating_system][RHEL][version][]=7.9", 2),
        ("[operating_system][RHEL][version][]=7.7&filter[system_profile][operating_system][RHEL][version][]=7.8", 5),
        ("[operating_system][RHEL][version][gt]=7.7", 7),
        ("[operating_system][RHEL][version][gte]=7.8", 7),
        ("[operating_system][RHEL][version][gte]=7.10", 4),
        ("[operating_system][RHEL][version][lte]=7.6", 0),
        ("[operating_system][RHEL][version][lte]=7.8", 5),
        (
            (
                "[operating_system][RHEL][version][]=7.7&filter[system_profile][operating_system][RHEL][version][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version]=7.9&filter[system_profile][host_type][]=edge"
            ),
            2,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=7"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=8"
            ),
            8,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=8"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.7"
            ),
            7,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=8.0"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version][eq][]=7.7"
            ),
            6,
        ),
        (
            (
                "[operating_system][RHEL][version][eq][]=7.8"
                "&filter[system_profile][operating_system][RHEL][version][gt][]=8.1"
                "&filter[system_profile][operating_system][RHEL][version][lt][]=9.1"
            ),
            4,
        ),
        (
            (
                "[operating_system][RHEL][version][gte][]=7.10"
                "&filter[system_profile][operating_system][RHEL][version][lte][]=7.10"
            ),
            1,
        ),
    ]

    for sp_filter_param, expected_host_count in sp_filter_param_list:
        with subtests.test(query_param=sp_filter_param):
            url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

            response_status, response_data = api_get(url)

            assert response_status == 200
            assert response_data["count"] == expected_host_count


def test_get_host_exists_found(db_create_host, api_get):
    insights_id = generate_uuid()
    created_host = db_create_host(extra_data={"insights_id": insights_id})

    url = build_host_exists_url(insights_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["id"] == str(created_host.id)


def test_get_host_exists_ignores_branch_id(db_create_host, api_get):
    insights_id = generate_uuid()
    created_host = db_create_host(extra_data={"insights_id": insights_id})

    url = f"{build_host_exists_url(insights_id)}&branch_id=54b80cb3-7fca-4444-9faf-aa43e8a560c3"
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["id"] == str(created_host.id)


def test_get_host_exists_not_found(api_get):
    url = build_host_exists_url(generate_uuid())
    response_status, _ = api_get(url)

    assert response_status == 404


def test_get_host_from_different_org(mocker, api_get):
    get_host_list_mock = mocker.patch("api.host.build_paginated_host_list_response")
    get_host_list_mock.return_value = {
        "total": 1,
        "count": 1,
        "page": 1,
        "per_page": 50,
        "results": [
            {
                "insights_id": "2d052fcb-04fd-4529-8052-bb924410eb8b",
                "subscription_manager_id": None,
                "satellite_id": None,
                "bios_uuid": None,
                "ip_addresses": None,
                "fqdn": None,
                "mac_addresses": None,
                "provider_id": None,
                "provider_type": None,
                "id": "12172925-832f-4341-b55f-557746ae2748",
                "account": "test",
                "org_id": "diff_test",
                "display_name": "12172925-832f-4341-b55f-557746ae2748",
                "ansible_host": None,
                "facts": [],
                "reporter": "test-reporter",
                "per_reporter_staleness": {
                    "test-reporter": {
                        "last_check_in": "2025-02-04T00:11:45.902105+00:00",
                        "stale_timestamp": "2025-02-05T05:11:45.902105+00:00",
                        "check_in_succeeded": True,
                        "stale_warning_timestamp": "2025-02-11T00:11:45.902105+00:00",
                        "culled_timestamp": "2025-02-18T00:11:45.902105+00:00",
                    }
                },
                "stale_timestamp": "2025-02-05T05:11:45.902627+00:00",
                "stale_warning_timestamp": "2025-02-11T00:11:45.902627+00:00",
                "culled_timestamp": "2025-02-18T00:11:45.902627+00:00",
                "created": "2025-02-04T00:11:45.902625+00:00",
                "updated": "2025-02-04T00:11:45.902627+00:00",
                "groups": [],
            }
        ],
    }

    url = build_hosts_url()
    response_status, _ = api_get(url)
    assert_response_status(response_status, 403)


def test_query_by_staleness(
    db_create_multiple_hosts: Callable[..., list[Host]],
    api_get: Callable[..., tuple[int, dict]],
    mocker: MockerFixture,
    subtests: SubTests,
) -> None:
    expected_staleness_results_map = {"fresh": 3, "stale": 4, "stale_warning": 2, "culled": 10}
    staleness_timestamp_map = {
        "fresh": now(),
        "stale": now() - timedelta(days=3),
        "stale_warning": now() - timedelta(days=10),
        "culled": now() - timedelta(days=35),
    }
    staleness_to_host_ids_map = {}

    # Create the hosts in each state
    for staleness, num_hosts in expected_staleness_results_map.items():
        # Patch the "now" function so the hosts are created in the desired state
        with mocker.patch("app.models.utils.datetime", **{"now.return_value": staleness_timestamp_map[staleness]}):
            staleness_to_host_ids_map[staleness] = [str(h.id) for h in db_create_multiple_hosts(how_many=num_hosts)]

    expected_staleness_results_map.pop("culled")

    # Test single staleness filters

    # "unknown" staleness filter should be ignored, so if it's the only filter,
    # then all non-culled hosts should be returned
    staleness_to_host_ids_map["unknown"] = sum(
        [staleness_to_host_ids_map[staleness] for staleness in ["fresh", "stale", "stale_warning"]], []
    )
    expected_staleness_results_map["unknown"] = len(staleness_to_host_ids_map["unknown"])

    for staleness, expected_count in expected_staleness_results_map.items():
        with subtests.test(staleness):
            url = build_hosts_url(query=f"?staleness={staleness}")
            expected_host_ids = set(staleness_to_host_ids_map[staleness])

            response_status, response_data = api_get(url)
            assert response_status == 200
            assert len(response_data["results"]) == expected_count
            assert {host["id"] for host in response_data["results"]} == expected_host_ids

    # Test combinations of staleness filters

    # "unknown" staleness filter should be ignored
    staleness_to_host_ids_map["unknown"] = []
    expected_staleness_results_map["unknown"] = 0

    for n in range(2, len(expected_staleness_results_map.keys()) + 1):
        # Test all possible combinations of `n` staleness filters
        for filters in combinations(expected_staleness_results_map.keys(), n):
            with subtests.test(", ".join(filters)):
                query = "?" + "&".join(f"staleness={staleness}" for staleness in filters)
                expected_count = sum(expected_staleness_results_map[staleness] for staleness in filters)
                expected_host_ids = set(sum([staleness_to_host_ids_map[staleness] for staleness in filters], []))
                logger.info(f"Testing query: {query}")

                response_status, response_data = api_get(build_hosts_url(query=query))
                assert response_status == 200
                assert len(response_data["results"]) == expected_count
                assert {host["id"] for host in response_data["results"]} == expected_host_ids


@pytest.mark.parametrize("system_type", ("conventional", "bootc", "edge", "cluster"))
def test_system_type_filter_valid_types(api_get, system_type):
    url = build_hosts_url(query=f"?system_type={system_type}")
    response_status, _ = api_get(url)

    assert response_status == 200


@pytest.mark.parametrize(
    "query_filter_param,matching_host_indexes",
    (
        ("?system_type=conventional", [0]),
        ("?system_type=bootc", [1]),
        ("?system_type=edge", [2, 4]),
        ("?system_type=cluster", [3]),
        ("?system_type=bootc&system_type=edge", [1, 2, 4]),
    ),
)
def test_system_type_happy_path(api_get, db_create_host, query_filter_param, matching_host_indexes):
    sp_facts = [
        {},
        {
            "system_profile_facts": {
                "bootc_status": {
                    "booted": {
                        "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223"
                    }
                }
            }
        },
        {"system_profile_facts": {"host_type": "edge"}},
        {"system_profile_facts": {"host_type": "cluster"}},
        {
            "system_profile_facts": {
                "host_type": "edge",
                "bootc_status": {
                    "booted": {
                        "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223"
                    }
                },
            }
        },
    ]
    host_ids = [str(db_create_host(extra_data=sp_fact).id) for sp_fact in sp_facts]

    url = build_hosts_url(query=query_filter_param)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == len(matching_host_indexes)
    for matching_host_index in matching_host_indexes:
        assert host_ids[matching_host_index] in [result["id"] for result in response_data["results"]]


def test_db_get_hosts_by_subman_id_multiple_hosts_org_filtering(db_get_hosts_by_subman_id, db_create_host):
    """Test that db_get_hosts_by_subman_id returns only hosts matching both subman_id and org_id."""
    subman_id = generate_uuid()
    org_id_1 = USER_IDENTITY["org_id"]
    org_id_2 = "different_org_id"

    # Create hosts with same subscription_manager_id in different orgs
    host1 = db_create_host(
        identity=USER_IDENTITY,
        extra_data={
            "org_id": org_id_1,
            "subscription_manager_id": subman_id,
            "insights_id": generate_uuid(),
        },
    )
    host2 = db_create_host(
        identity={"account_number": "123", "org_id": org_id_2},
        extra_data={
            "org_id": org_id_2,
            "subscription_manager_id": subman_id,
            "insights_id": generate_uuid(),
        },
    )

    # Test filtering by first org_id
    hosts_org_1 = db_get_hosts_by_subman_id(subman_id, org_id_1)
    assert len(hosts_org_1) == 1
    assert hosts_org_1[0].id == host1.id
    assert hosts_org_1[0].org_id == org_id_1

    # Test filtering by second org_id
    hosts_org_2 = db_get_hosts_by_subman_id(subman_id, org_id_2)
    assert len(hosts_org_2) == 1
    assert hosts_org_2[0].id == host2.id
    assert hosts_org_2[0].org_id == org_id_2

    # Test default behavior (should use SYSTEM_IDENTITY org_id)
    hosts_default = db_get_hosts_by_subman_id(subman_id)
    expected_org_id = SYSTEM_IDENTITY["org_id"]
    assert len(hosts_default) == 1
    assert hosts_default[0].id == host1.id
    assert hosts_default[0].org_id == expected_org_id


def test_db_get_hosts_by_subman_id_multiple_in_same_org(db_get_hosts_by_subman_id, db_create_host):
    """Test db_get_hosts_by_subman_id with multiple hosts having same subman_id in same org."""
    subman_id = generate_uuid()
    org_id = USER_IDENTITY["org_id"]

    # Create multiple hosts with same subscription_manager_id in same org
    host1 = db_create_host(
        identity=USER_IDENTITY,
        extra_data={
            "org_id": org_id,
            "subscription_manager_id": subman_id,
            "insights_id": generate_uuid(),
        },
    )
    host2 = db_create_host(
        identity=USER_IDENTITY,
        extra_data={
            "org_id": org_id,
            "subscription_manager_id": subman_id,
            "insights_id": generate_uuid(),
        },
    )

    hosts = db_get_hosts_by_subman_id(subman_id, org_id)
    assert len(hosts) == 2
    host_ids = {host.id for host in hosts}
    assert host_ids == {host1.id, host2.id}


@pytest.mark.parametrize(
    "field_key_level_1,field_key_level_2",
    (
        ("sap", "sap_system"),
        ("ibm_db2", "is_running"),
        ("intersystems", "is_intersystems"),
        ("oracle_db", "is_running"),
    ),
)
def test_api_hosts_get_empty_boolean_workloads_fields(db_create_host, api_get, field_key_level_1, field_key_level_2):
    """Test that empty strings are not allowed for boolean and integer fields."""
    db_create_host()

    # Test with empty string without eq comparator
    url = build_hosts_url(query=f"?filter[system_profile][{field_key_level_1}][{field_key_level_2}]=")
    response_status, response_data = api_get(url)
    assert response_status == 400
    assert f" is an invalid value for field {field_key_level_2}" in response_data["detail"]

    # Test with empty string with eq comparator
    url = build_hosts_url(query=f"?filter[system_profile][{field_key_level_1}][{field_key_level_2}][eq]=")
    response_status, response_data = api_get(url)
    assert response_status == 400
    assert f" is an invalid value for field {field_key_level_2}" in response_data["detail"]


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "filter[system_profile][workloads][sap][is]=not_nil&filter[system_profile][workloads][ansible][is]=not_nil",
        "filter[system_profile][workloads][rhel_ai][is]=nil&filter[system_profile][workloads][ansible][is]=not_nil",
        "filter[system_profile][workloads][mssql][]=not_nil&filter[system_profile][workloads][sap][]=not_nil",
    ),
)
def test_query_workload_top_level_presence_filters_use_or_logic(db_create_host, api_get, sp_filter_param):
    """
    Verifies that filtering by top-level workload types (existence)
    broadens the results using OR logic.
    """
    sap_host_id = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "workloads": {"sap": {"sap_system": True}, "rhel_ai": {"rhel_ai_version_id": "v1.1.3"}}
                }
            }
        ).id
    )
    ansible_host_id = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "workloads": {
                        "ansible": {"controller_version": "1.2"},
                        "rhel_ai": {"rhel_ai_version_id": "v1.1.3"},
                    }
                }
            }
        ).id
    )
    mssql_host_id = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "workloads": {"mssql": {"version": "2022"}, "rhel_ai": {"rhel_ai_version_id": "v1.1.3"}}
                }
            }
        ).id
    )

    no_rhel_host_id = str(db_create_host(extra_data={"system_profile_facts": {"workloads": {}}}).id)

    url = build_hosts_url(query=f"?{sp_filter_param}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]

    assert len(response_ids) == 2

    if "sap" in sp_filter_param:
        assert sap_host_id in response_ids
    if "ansible" in sp_filter_param:
        assert ansible_host_id in response_ids
    if "mssql" in sp_filter_param:
        assert mssql_host_id in response_ids
    if "rhel_ai" in sp_filter_param:
        assert no_rhel_host_id in response_ids


def test_query_workload_specific_properties_across_workloads_still_use_and_logic(db_create_host, api_get):
    """Drill-down filters on different workloads remain AND (Case 2)."""
    sap_ver = "1.00.122.04.1478575636"
    mssql_ver = "15.2.0"

    both = {
        "system_profile_facts": {
            "workloads": {
                "sap": {"sap_system": True, "version": sap_ver},
                "mssql": {"version": mssql_ver},
            }
        }
    }
    sap_only = {
        "system_profile_facts": {
            "workloads": {"sap": {"sap_system": True, "version": sap_ver}},
        }
    }
    mssql_only = {
        "system_profile_facts": {
            "workloads": {"mssql": {"version": mssql_ver}},
        }
    }

    both_id = str(db_create_host(extra_data=both).id)
    sap_only_id = str(db_create_host(extra_data=sap_only).id)
    mssql_only_id = str(db_create_host(extra_data=mssql_only).id)

    url = build_hosts_url(
        query=f"?filter[system_profile][workloads][sap][version]={sap_ver}"
        f"&filter[system_profile][workloads][mssql][version]={mssql_ver}"
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert both_id in response_ids
    assert sap_only_id not in response_ids
    assert mssql_only_id not in response_ids


def test_mixed_workload_property_and_type_no_matches(db_create_host, api_get):
    db_create_host(extra_data={"system_profile_facts": {"workloads": {"sap": {"sids": ["H2O"]}}}})
    db_create_host(extra_data={"system_profile_facts": {"workloads": {"rhel_ai": {"variant": "RHEL AI"}}}})

    query = "?filter[system_profile][sap_sids][contains][]=H2O&filter[system_profile][rhel_ai][is][]=not_nil"

    url = build_hosts_url(query)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == []


def test_workloads_nil_filter_uses_not_exists(db_create_host, api_get):
    """Nil workloads filters use NOT EXISTS to match hosts with no matching
    system_profiles_dynamic row. Also covers partial data where the parent key exists
    but the leaf field is absent.
    """
    empty_sp_host = str(db_create_host(extra_data={"system_profile_facts": {}}).id)
    sap_true_host = str(
        db_create_host(extra_data={"system_profile_facts": {"workloads": {"sap": {"sap_system": True}}}}).id
    )
    # workloads.sap exists but sap_system is not set — should match nil
    sap_no_field_host = str(db_create_host(extra_data={"system_profile_facts": {"workloads": {"sap": {}}}}).id)

    url = build_hosts_url(query="?filter[system_profile][sap_system][is]=nil")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert empty_sp_host in response_ids
    assert sap_no_field_host in response_ids
    assert sap_true_host not in response_ids


def test_workloads_string_not_nil_finds_hosts_with_field_set(db_create_host, api_get):
    """String/wildcard not_nil filter (e.g. ansible controller_version) should find hosts with the field set."""
    match_host = str(
        db_create_host(
            extra_data={"system_profile_facts": {"workloads": {"ansible": {"controller_version": "4.5.0"}}}}
        ).id
    )
    ansible_no_version = str(db_create_host(extra_data={"system_profile_facts": {"workloads": {"ansible": {}}}}).id)
    no_ansible = str(
        db_create_host(extra_data={"system_profile_facts": {"workloads": {"sap": {"sap_system": True}}}}).id
    )

    url = build_hosts_url(query="?filter[system_profile][workloads][ansible][controller_version][is]=not_nil")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert match_host in response_ids
    assert ansible_no_version not in response_ids
    assert no_ansible not in response_ids


def test_workloads_wildcard_glob_uses_ilike(db_create_host, api_get):
    """Wildcard field with glob pattern (e.g. version=15.*) should use ILIKE, not @> containment."""
    host_15_3 = str(
        db_create_host(extra_data={"system_profile_facts": {"workloads": {"mssql": {"version": "15.3"}}}}).id
    )
    host_15_10 = str(
        db_create_host(extra_data={"system_profile_facts": {"workloads": {"mssql": {"version": "15.10"}}}}).id
    )
    host_14_9 = str(
        db_create_host(extra_data={"system_profile_facts": {"workloads": {"mssql": {"version": "14.9"}}}}).id
    )

    url = build_hosts_url(query="?filter[system_profile][workloads][mssql][version]=15.*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert host_15_3 in response_ids
    assert host_15_10 in response_ids
    assert host_14_9 not in response_ids


def test_no_hosts_in_org(api_get):
    """Test no hosts are returned if for empty organization."""

    url = build_hosts_url()
    response_status, response_data = api_get(url, identity=IDENTITY_WITHOUT_HOSTS)
    assert response_status == 200
    assert response_data["results"] == []
    assert response_data["count"] == response_data["total"] == 0


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("hello", "hello"),
        ("hello%world", "hello\\%world"),
        ("hello_world", "hello\\_world"),
        ("hello\\world", "hello\\\\world"),
        ("hello*world", "hello%world"),
        ("hello\\%_*world", "hello\\\\\\%\\_%world"),
        (123, 123),
        (None, None),
    ],
)
def test_escape_ilike_value(input_val: Any, expected: Any) -> None:
    assert escape_ilike_value(input_val) == expected


@pytest.mark.parametrize(
    "filter_field,data_key,is_system_profile",
    [
        ("display_name", "display_name", False),
        ("hostname_or_id", "fqdn", False),
        ("insights_client_version", "insights_client_version", True),
    ],
)
def test_wildcard_escaping(
    filter_field: str,
    data_key: str,
    is_system_profile: bool,
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    # Create hosts with special characters
    if is_system_profile:
        host_percent = db_create_host(extra_data={"system_profile_facts": {data_key: "Version%1"}})
        host_underscore = db_create_host(extra_data={"system_profile_facts": {data_key: "Version_1"}})
        host_backslash = db_create_host(extra_data={"system_profile_facts": {data_key: "Version\\1"}})
        host_asterisk = db_create_host(extra_data={"system_profile_facts": {data_key: "VersionX1"}})
        prefix = "Version"
    else:
        host_percent = db_create_host(extra_data={data_key: "Host%1"})
        host_underscore = db_create_host(extra_data={data_key: "Host_1"})
        host_backslash = db_create_host(extra_data={data_key: "Host\\1"})
        host_asterisk = db_create_host(extra_data={data_key: "HostX1"})
        prefix = "Host"

    # 1. Query for percent: should only match host_percent, not host_underscore or host_backslash or host_asterisk
    if is_system_profile:
        url = build_hosts_url(query=f"?filter[system_profile][{filter_field}]={prefix}%251")
    else:
        url = build_hosts_url(query=f"?{filter_field}={prefix}%251")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 2. Query for underscore: should only match host_underscore
    if is_system_profile:
        url = build_hosts_url(query=f"?filter[system_profile][{filter_field}]={prefix}_1")
    else:
        url = build_hosts_url(query=f"?{filter_field}={prefix}_1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_underscore.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 3. Query for backslash: should only match host_backslash
    if is_system_profile:
        url = build_hosts_url(query=f"?filter[system_profile][{filter_field}]={prefix}%5C1")
    else:
        url = build_hosts_url(query=f"?{filter_field}={prefix}%5C1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_backslash.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_underscore.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 4. Query for asterisk: should match host_asterisk, host_percent, host_underscore, host_backslash
    if is_system_profile:
        url = build_hosts_url(query=f"?filter[system_profile][{filter_field}]={prefix}*1")
    else:
        url = build_hosts_url(query=f"?{filter_field}={prefix}*1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_asterisk.id) in ids
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) in ids
    assert str(host_backslash.id) in ids


def test_get_host_by_null_and_named_namespace_same_key_uses_and(db_create_host, api_get, subtests):
    """
    Verify AND logic for tags with null namespace vs named namespace with the same key.
    Empty/null namespace must be treated as distinct from named namespaces when grouping by identity.
    Query: key1=val1 AND ns1/key1=val1
    """
    tags_data_list = [
        {"tags": {"null": {"key1": ["val1"]}}},
        {"tags": {"ns1": {"key1": ["val1"]}}},
        {"tags": {"null": {"key1": ["val1"]}, "ns1": {"key1": ["val1"]}}},
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=key1=val1&tags=ns1/key1=val1")

    api_pagination_test(api_get, subtests, url, expected_total=1)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host_ids[2]


def test_get_host_by_same_namespace_different_keys_multiple_values(db_create_host, api_get, subtests):
    """
    Verify tags in the same namespace but different keys are AND'd together,
    with OR logic applied within each key identity.
    Query: (ns1/key1=val1 OR ns1/key1=val2) AND (ns1/key2=valA OR ns1/key2=valB)
    """
    tags_data_list = [
        {"tags": {"ns1": {"key1": ["val1"], "key2": ["valA"]}}},  # matches (val1, valA)
        {"tags": {"ns1": {"key1": ["val2"], "key2": ["valB"]}}},  # matches (val2, valB)
        {"tags": {"ns1": {"key1": ["val1"], "key2": ["valC"]}}},  # no match (valC)
        {"tags": {"ns1": {"key1": ["val3"], "key2": ["valA"]}}},  # no match (val3)
        {"tags": {"ns1": {"key1": ["val1"]}}},  # no match (missing key2)
    ]

    host_ids = [str(db_create_host(extra_data=tags_data).id) for tags_data in tags_data_list]
    url = build_hosts_url(query="?tags=ns1/key1=val1&tags=ns1/key1=val2&tags=ns1/key2=valA&tags=ns1/key2=valB")

    api_pagination_test(api_get, subtests, url, expected_total=2)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    result_ids = {result["id"] for result in response_data["results"]}
    assert result_ids == {host_ids[0], host_ids[1]}
