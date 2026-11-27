from tests.helpers.api_utils import api_pagination_test
from tests.helpers.api_utils import assert_host_lists_equal
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_expected_host_list
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


def test_get_hosts_returns_both_when_shared_insights_id_and_owner_were_cached(flask_app, db_create_host, api_get):
    """A cached system-client lookup must not hide a second host with the same insights ID and owner."""
    from flask_caching import Cache

    import api.cache as cache_module
    import api.host as host_api
    from api.cache_key import make_system_cache_key
    from app.queue.host_mq import cache_ingested_system

    insights_id = generate_uuid()
    owner_id = SYSTEM_IDENTITY["system"]["cn"]
    org_id = SYSTEM_IDENTITY["org_id"]
    hosts = [
        db_create_host(
            SYSTEM_IDENTITY,
            extra_data={
                "insights_id": insights_id,
                "subscription_manager_id": generate_uuid(),
                "system_profile_facts": {"owner_id": owner_id},
            },
        )
        for _ in range(2)
    ]
    host_ids = {str(host.id) for host in hosts}
    for host in hosts:
        assert host.static_system_profile is not None
        assert str(host.static_system_profile.owner_id) == owner_id

    simple_cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
    simple_cache.init_app(flask_app.app, config={"CACHE_TYPE": "SimpleCache"})
    original_cache = cache_module.CACHE
    original_host_cache = host_api.CACHE
    cache_module.CACHE = simple_cache
    host_api.CACHE = simple_cache

    system_key = make_system_cache_key(insights_id, org_id, owner_id, generation=0)
    simple_cache.set(system_key, {"id": str(hosts[1].id), "insights_id": insights_id})

    try:
        cache_ingested_system(
            {
                "id": str(hosts[1].id),
                "org_id": org_id,
                "system_profile": {"owner_id": owner_id},
            },
            insights_id,
            created=False,
            groups=[],
        )
        assert simple_cache.get(system_key) is None

        response_status, response_data = api_get(build_hosts_url(query=f"?insights_id={insights_id}"), SYSTEM_IDENTITY)
        assert_response_status(response_status, 200)
        assert response_data["count"] == 2
        assert {host["id"] for host in response_data["results"]} == host_ids
    finally:
        cache_module.CACHE = original_cache
        host_api.CACHE = original_host_cache


def test_query_using_display_name(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0]])
    url = build_hosts_url(query=f"?display_name={created_hosts[0].display_name.upper()}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_fqdn_two_results(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[0], created_hosts[1]])

    url = build_hosts_url(query=f"?fqdn={created_hosts[0].fqdn.upper()}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_fqdn_one_result(mq_create_three_specific_hosts, api_get):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list([created_hosts[2]])
    url = build_hosts_url(query=f"?fqdn={created_hosts[2].fqdn}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert_host_lists_equal(expected_host_list, response_data["results"])


def test_query_using_display_name_substring(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    expected_host_list = build_expected_host_list(created_hosts)
    host_name_substr = created_hosts[0].display_name[:4]
    url = build_hosts_url(query=f"?display_name={host_name_substr}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=len(created_hosts))

    assert response_status == 200
    assert_host_lists_equal(expected_host_list, response_data["results"])

    page_ids = []
    for page in range(1, len(created_hosts) + 1):
        status, data = api_get(url, query_parameters={"page": page, "per_page": 1})
        assert status == 200
        assert data["total"] == len(created_hosts)
        assert data["count"] == len(data["results"]) == 1
        page_ids.append(data["results"][0]["id"])
    assert len(page_ids) == len(set(page_ids))
    assert set(page_ids) == {host.id for host in created_hosts}


def test_query_using_display_name_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[0].display_name}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=2)

    assert response_status == 200
    assert len(response_data["results"]) == 2


def test_query_using_fqdn_as_hostname(mq_create_three_specific_hosts, api_get, subtests):
    created_hosts = mq_create_three_specific_hosts
    url = build_hosts_url(query=f"?hostname_or_id={created_hosts[2].display_name}")

    response_status, response_data = api_get(url)
    api_pagination_test(api_get, subtests, url, expected_total=1)

    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_db_get_hosts_by_display_name_duplicate_across_orgs(db_get_hosts_by_display_name, db_create_host):
    """Test that db_get_hosts_by_display_name correctly filters by org_id when display names are duplicated."""
    display_name = "duplicate_name"
    org_id_1 = USER_IDENTITY["org_id"]
    org_id_2 = "different_org_id"

    # Create hosts with same display name in different orgs
    host1 = db_create_host(identity=USER_IDENTITY, extra_data={"org_id": org_id_1, "display_name": display_name})
    host2 = db_create_host(
        identity={"account_number": "123", "org_id": org_id_2},
        extra_data={"org_id": org_id_2, "display_name": display_name},
    )

    # Test filtering by first org_id
    hosts_org_1 = db_get_hosts_by_display_name(display_name, org_id_1)
    assert len(hosts_org_1) == 1
    assert hosts_org_1[0].id == host1.id
    assert hosts_org_1[0].org_id == org_id_1

    # Test filtering by second org_id
    hosts_org_2 = db_get_hosts_by_display_name(display_name, org_id_2)
    assert len(hosts_org_2) == 1
    assert hosts_org_2[0].id == host2.id
    assert hosts_org_2[0].org_id == org_id_2

    # Test default behavior (should use SYSTEM_IDENTITY org_id)
    hosts_default = db_get_hosts_by_display_name(display_name)
    # This should return hosts from SYSTEM_IDENTITY org_id
    expected_org_id = SYSTEM_IDENTITY["org_id"]
    assert len(hosts_default) == 1
    assert hosts_default[0].id == host1.id
    assert hosts_default[0].org_id == expected_org_id


def test_db_get_hosts_by_display_name_multiple_in_same_org(db_get_hosts_by_display_name, db_create_host):
    """Test db_get_hosts_by_display_name with multiple hosts having same display name in same org."""
    display_name = "same_name"
    org_id = USER_IDENTITY["org_id"]

    # Create multiple hosts with same display name in same org
    host1 = db_create_host(identity=USER_IDENTITY, extra_data={"org_id": org_id, "display_name": display_name})
    host2 = db_create_host(identity=USER_IDENTITY, extra_data={"org_id": org_id, "display_name": display_name})

    hosts = db_get_hosts_by_display_name(display_name, org_id)
    assert len(hosts) == 2
    host_ids = {host.id for host in hosts}
    assert host_ids == {host1.id, host2.id}
