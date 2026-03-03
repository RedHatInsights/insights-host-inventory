import pytest

from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_count_url


def test_dont_get_only_culled(api_get):
    url = build_hosts_url(query="?staleness=culled")
    response_status, _ = api_get(url)

    assert response_status == 400


def test_fail_patch_culled_host(mq_create_deleted_hosts, api_patch):
    culled_host = mq_create_deleted_hosts["culled"]

    url = build_hosts_url(host_list_or_id=[culled_host])
    response_status, _ = api_patch(url, {"display_name": "patched"})

    assert response_status == 404


def test_patch_works_on_non_culled(mq_create_hosts_in_all_states, api_patch):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_hosts_url(host_list_or_id=[fresh_host])
    response_status, _ = api_patch(url, {"display_name": "patched"})

    assert response_status == 200


def test_patch_facts_ignores_culled(mq_create_deleted_hosts, api_patch):
    culled_host = mq_create_deleted_hosts["culled"]
    url = build_facts_url(host_list_or_id=[culled_host], namespace="ns1")
    response_status, _ = api_patch(url, {"ARCHITECTURE": "patched"})

    assert response_status == 404


def test_patch_facts_works_on_non_culled(mq_create_hosts_in_all_states, api_patch):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_facts_url(host_list_or_id=[fresh_host], namespace="ns1")
    response_status, response_data = api_patch(url, {"ARCHITECTURE": "patched"})

    assert response_status == 200


def test_put_facts_ignores_culled(mq_create_deleted_hosts, api_put):
    culled_host = mq_create_deleted_hosts["culled"]

    url = build_facts_url(host_list_or_id=[culled_host], namespace="ns1")

    response_status, _ = api_put(url, {"ARCHITECTURE": "patched"})

    assert response_status == 404


def test_put_facts_works_on_non_culled(mq_create_hosts_in_all_states, api_put):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_facts_url(host_list_or_id=[fresh_host], namespace="ns1")
    response_status, _ = api_put(url, {"ARCHITECTURE": "patched"})

    assert response_status == 200


def test_delete_ignores_culled(mq_create_deleted_hosts, api_delete_host):
    culled_host = mq_create_deleted_hosts["culled"]

    response_status, _ = api_delete_host(culled_host.id)

    assert response_status == 404


def test_delete_works_on_non_culled(mq_create_hosts_in_all_states, api_delete_host):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    response_status, _ = api_delete_host(fresh_host.id)

    assert response_status == 200


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_get_host_by_id_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_hosts_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_tags_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_host_tags_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_tags_count_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_tags_count_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_system_profile_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_system_profile_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400
