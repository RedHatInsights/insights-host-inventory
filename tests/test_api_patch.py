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
from tests.utils.db_utils import db_host
from tests.utils.mq_utils import assert_patch_event_is_valid


@pytest.mark.parametrize(
    "patch_doc",
    [
        {"ansible_host": "NEW_ansible_host"},
        {"ansible_host": ""},
        {"display_name": "fred_flintstone"},
        {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"},
    ],
)
def test_update_fields(patch_doc, db_create_host, db_get_host, api_patch_host):
    host = db_create_host()

    response_status, response_data = api_patch_host(f"{HOST_URL}/{host.id}", patch_doc)

    assert_response_status(response_status, expected_status=200)

    record = db_get_host(host.id)

    for key in patch_doc:
        assert getattr(record, key) == patch_doc[key]


def test_patch_with_branch_id_parameter(db_create_multiple_hosts, api_patch_host):
    patch_doc = {"display_name": "branch_id_test"}

    hosts = db_create_multiple_hosts(how_many=5)

    host_ids = build_host_id_list_for_url(hosts)

    response_status, response_data = api_patch_host(
        f"{HOST_URL}/{host_ids}", patch_doc, query_parameters={"branch_id": 123}
    )

    assert_response_status(response_status, expected_status=200)


def test_update_fields_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_patch_host):
    patch_doc = {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"}

    hosts = db_create_multiple_hosts(how_many=5)

    host_ids = build_host_id_list_for_url(hosts)

    response_status, response_data = api_patch_host(f"{HOST_URL}/{host_ids}", patch_doc)

    assert_response_status(response_status, expected_status=200)

    host_id_list = [host.id for host in hosts]
    hosts = db_get_hosts(host_id_list)

    for host in hosts:
        for key in patch_doc:
            assert getattr(host, key) == patch_doc[key]


def test_patch_on_non_existent_host(api_patch_host):
    non_existent_id = generate_uuid()

    patch_doc = {"ansible_host": "NEW_ansible_host"}

    response_status, response_data = api_patch_host(f"{HOST_URL}/{non_existent_id}", patch_doc)

    assert_response_status(response_status, expected_status=404)


def test_patch_on_multiple_hosts_with_some_non_existent(db_create_host, api_patch_host):
    non_existent_id = generate_uuid()
    host = db_create_host()

    patch_doc = {"ansible_host": "NEW_ansible_host"}

    response_status, response_data = api_patch_host(f"{HOST_URL}/{non_existent_id},{host.id}", patch_doc)

    assert_response_status(response_status, expected_status=200)


@pytest.mark.parametrize(
    "invalid_data",
    [{"ansible_host": "a" * 256}, {"ansible_host": None}, {}, {"display_name": None}, {"display_name": ""}],
)
def test_invalid_data(invalid_data, db_create_host, api_patch_host):
    host = db_create_host()

    response_status, response_data = api_patch_host(f"{HOST_URL}/{host.id}", invalid_data)

    assert_response_status(response_status, expected_status=400)


def test_invalid_host_id(db_create_host, api_patch_host, subtests):
    host = db_create_host()

    patch_doc = {"display_name": "branch_id_test"}
    host_id_lists = ["notauuid", f"{host.id},notauuid"]

    for host_id_list in host_id_lists:
        with subtests.test(host_id_list=host_id_list):
            response_status, response_data = api_patch_host(f"{HOST_URL}/{host_id_list}", patch_doc)
            assert_response_status(response_status, expected_status=400)


def test_patch_produces_update_event_no_request_id(
    event_datetime_mock, event_producer_mock, db_create_host, db_get_host, api_patch_host
):
    patch_doc = {"display_name": "patch_event_test"}

    host = db_host()
    created_host = db_create_host(host)

    response_status, response_data = api_patch_host(f"{HOST_URL}/{created_host.id}", patch_doc)
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id="-1",
        expected_timestamp=event_datetime_mock,
    )


def test_patch_produces_update_event_with_request_id(
    event_datetime_mock, event_producer_mock, db_create_host, db_get_host, api_patch_host
):
    patch_doc = {"display_name": "patch_event_test"}
    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    host = db_host()
    created_host = db_create_host(host)

    response_status, response_data = api_patch_host(f"{HOST_URL}/{created_host.id}", patch_doc, extra_headers=headers)
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id=request_id,
        expected_timestamp=event_datetime_mock,
    )


def test_add_facts_without_fact_dict(api_patch_host, db_create_host):
    facts_url = build_facts_url(1, "ns1")
    response_status, response_data = api_patch_host(facts_url, None)

    assert_error_response(response_data, expected_status=400, expected_detail="Request body is not valid JSON")


def test_add_facts_to_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_patch_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_add = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace)

    response_status, response_data = api_patch_host(facts_url, facts_to_add)

    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace].update(facts_to_add)

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


def test_add_facts_to_multiple_hosts_with_branch_id(db_create_multiple_hosts, db_get_hosts, api_patch_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace) + "?" + "branch_id=1234"

    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace].update(facts_to_update)

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


def test_add_facts_to_multiple_hosts_including_nonexistent_host(
    db_create_multiple_hosts, db_get_hosts, api_patch_host
):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    url_host_id_list = f"{build_host_id_list_for_url(created_hosts)},{generate_uuid()},{generate_uuid()}"
    facts_url = f"{HOST_URL}/{url_host_id_list}/facts/{facts_namespace}"

    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)


def test_add_facts_to_multiple_hosts_overwrite_empty_key_value_pair(
    db_create_multiple_hosts, db_get_hosts, api_patch_host
):
    facts_namespace = "ns1"
    facts = {facts_namespace: {}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(created_hosts, facts_namespace)

    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=200)

    facts[facts_namespace].update(facts_to_update)

    assert all(host.facts == facts for host in db_get_hosts(host_id_list))


def test_add_facts_to_multiple_hosts_add_empty_fact_set(db_create_multiple_hosts, api_patch_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    facts_url = build_facts_url(created_hosts, facts_namespace)

    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)


def test_add_facts_to_namespace_that_does_not_exist(db_create_multiple_hosts, api_patch_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    facts_url = build_facts_url(created_hosts, "imanonexistentnamespace")

    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)


@pytest.mark.system_culling
def test_add_facts_to_multiple_culled_hosts(db_create_multiple_hosts, db_get_hosts, api_patch_host):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}
    facts_to_update = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    staleness_timestamps = get_staleness_timestamps()

    created_hosts = db_create_multiple_hosts(
        how_many=2, extra_data={"facts": facts, "stale_timestamp": staleness_timestamps["culled"]}
    )

    facts_url = build_facts_url(created_hosts, facts_namespace)

    # Try to replace the facts on a host that has been marked as culled
    response_status, response_data = api_patch_host(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=400)
