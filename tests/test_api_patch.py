#!/usr/bin/env python
import pytest

from .test_utils import assert_patch_event_is_valid
from .test_utils import assert_response_status
from .test_utils import build_host_id_list_for_url
from .test_utils import db_host
from .test_utils import generate_uuid


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

    response_status = api_patch_host(host.id, patch_doc)

    assert_response_status(response_status, expected_status=200)

    record = db_get_host(host.id)

    for key in patch_doc:
        assert getattr(record, key) == patch_doc[key]


def test_patch_with_branch_id_parameter(db_create_multiple_hosts, api_patch_host):
    patch_doc = {"display_name": "branch_id_test"}

    hosts = db_create_multiple_hosts(how_many=5)

    url_host_id_list = build_host_id_list_for_url(hosts)

    response_status = api_patch_host(url_host_id_list, patch_doc, query_parameters={"branch_id": 123})

    assert_response_status(response_status, expected_status=200)


def test_update_fields_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_patch_host):
    patch_doc = {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"}

    hosts = db_create_multiple_hosts(how_many=5)

    url_host_id_list = build_host_id_list_for_url(hosts)

    response_status = api_patch_host(url_host_id_list, patch_doc)

    assert_response_status(response_status, expected_status=200)

    host_id_list = [host.id for host in hosts]
    hosts = db_get_hosts(host_id_list)

    for host in hosts:
        for key in patch_doc:
            assert getattr(host, key) == patch_doc[key]


def test_patch_on_non_existent_host(api_patch_host):
    non_existent_id = generate_uuid()

    patch_doc = {"ansible_host": "NEW_ansible_host"}

    response_status = api_patch_host(non_existent_id, patch_doc)

    assert_response_status(response_status, expected_status=404)


def test_patch_on_multiple_hosts_with_some_non_existent(db_create_host, api_patch_host):
    non_existent_id = generate_uuid()
    host = db_create_host()

    patch_doc = {"ansible_host": "NEW_ansible_host"}

    response_status = api_patch_host(f"{non_existent_id},{host.id}", patch_doc)

    assert_response_status(response_status, expected_status=200)


@pytest.mark.parametrize(
    "invalid_data",
    [{"ansible_host": "a" * 256}, {"ansible_host": None}, {}, {"display_name": None}, {"display_name": ""}],
)
def test_invalid_data(invalid_data, db_create_host, api_patch_host):
    host = db_create_host()

    response_status = api_patch_host(host.id, invalid_data)

    assert_response_status(response_status, expected_status=400)


def test_invalid_host_id(db_create_host, api_patch_host, subtests):
    host = db_create_host()

    patch_doc = {"display_name": "branch_id_test"}
    host_id_lists = ["notauuid", f"{host.id},notauuid"]

    for host_id_list in host_id_lists:
        with subtests.test(host_id_list=host_id_list):
            response_status = api_patch_host(host_id_list, patch_doc)
            assert_response_status(response_status, expected_status=400)


def test_patch_produces_update_event_no_request_id(
    event_datetime_mock, event_producer_mock, db_create_host, db_get_host, api_patch_host
):
    patch_doc = {"display_name": "patch_event_test"}

    host = db_host()
    created_host = db_create_host(host)

    response_status = api_patch_host(created_host.id, patch_doc)
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

    response_status = api_patch_host(created_host.id, patch_doc, headers=headers)
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id=request_id,
        expected_timestamp=event_datetime_mock,
    )
