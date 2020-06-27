#!/usr/bin/env python
import pytest

from tests.utils import generate_uuid
from tests.utils import get_staleness_timestamps
from tests.utils.api_utils import assert_error_response
from tests.utils.api_utils import assert_response_status
from tests.utils.api_utils import build_facts_url
from tests.utils.api_utils import build_host_id_list_for_url
from tests.utils.api_utils import get_id_list_from_hosts
from tests.utils.api_utils import HOST_URL


def test_replace_facts_to_multiple_hosts_with_branch_id(db_create_multiple_hosts, db_get_hosts, api_put_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace) + "?" + "branch_id=1234"

    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace] = facts_to_update

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


def test_replace_facts_to_multiple_hosts_including_nonexistent_host(
    db_create_multiple_hosts, db_get_hosts, api_put_host
):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    url_host_id_list = f"{build_host_id_list_for_url(created_hosts)},{generate_uuid()},{generate_uuid()}"
    facts_url = f"{HOST_URL}/{url_host_id_list}/facts/{facts_namespace}"

    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)


def test_replace_facts_to_multiple_hosts_with_empty_key_value_pair(
    db_create_multiple_hosts, db_get_hosts, api_put_host
):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace)

    # Set the value in the namespace to an empty fact set
    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace] = facts_to_update

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


def test_replace_facts_to_namespace_that_does_not_exist(db_create_multiple_hosts, api_patch_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    facts_url = build_facts_url(created_hosts, "imanonexistentnamespace")

    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)


def test_replace_facts_without_fact_dict(api_put_host):
    facts_url = build_facts_url(1, "ns1")
    response_status, response_data = api_put_host(facts_url, None)

    assert_error_response(response_data, expected_status=400, expected_detail="Request body is not valid JSON")


def test_replace_facts_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_put_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace)

    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace] = facts_to_update

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


def test_replace_empty_facts_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_put_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace)

    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace] = facts_to_update

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))

    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace] = facts_to_update

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


@pytest.mark.system_culling
def test_replace_facts_on_multiple_culled_hosts(db_create_multiple_hosts, db_get_hosts, api_put_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    staleness_timestamps = get_staleness_timestamps()

    created_hosts = db_create_multiple_hosts(
        how_many=2, extra_data={"facts": facts, "stale_timestamp": staleness_timestamps["culled"]}
    )

    facts_url = build_facts_url(created_hosts, facts_namespace)

    # Try to replace the facts on a host that has been marked as culled
    response_status, response_data = api_put_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)
