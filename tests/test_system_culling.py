#!/usr/bin/env python
from datetime import timedelta
from unittest import mock

import pytest

from app import db
from app import threadctx
from app import UNKNOWN_REQUEST_ID_VALUE
from host_reaper import run as host_reaper_run
from tests.helpers.api_utils import assert_host_ids_in_response
from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import HOST_URL
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.test_utils import assert_system_culling_data
from tests.helpers.test_utils import get_staleness_timestamps
from tests.helpers.test_utils import minimal_host
from tests.test_api_utils import now


def test_with_stale_timestamp(mq_create_or_update_host, api_get):
    stale_timestamp = now()
    reporter = "some reporter"

    host = minimal_host(fqdn="matching fqdn", stale_timestamp=stale_timestamp.isoformat(), reporter=reporter)

    created_host = mq_create_or_update_host(host)
    assert_system_culling_data(created_host.data(), stale_timestamp, reporter)

    updated_host = mq_create_or_update_host(host)
    assert_system_culling_data(updated_host.data(), stale_timestamp, reporter)

    response_status, response_data = api_get(HOST_URL)
    assert response_status == 200
    assert_system_culling_data(response_data["results"][0], stale_timestamp, reporter)

    response_status, response_data = api_get(build_hosts_url(created_host.id))
    assert response_status == 200
    assert_system_culling_data(response_data["results"][0], stale_timestamp, reporter)


def test_dont_get_only_culled(mq_create_hosts_in_all_states, api_get):
    response_status, response_data = api_get(HOST_URL, query_parameters={"staleness": "culled"})

    assert response_status == 400


def test_get_only_fresh(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states
    response_status, response_data = api_get(HOST_URL, query_parameters={"staleness": "fresh"})

    assert response_status == 200
    assert_host_ids_in_response(response_data, [created_hosts["fresh"]])


def test_get_only_stale(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states
    response_status, response_data = api_get(HOST_URL, query_parameters={"staleness": "stale"})

    assert response_status == 200
    assert_host_ids_in_response(response_data, [created_hosts["stale"]])


def test_get_only_stale_warning(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states
    response_status, response_data = api_get(HOST_URL, query_parameters={"staleness": "stale_warning"})

    assert response_status == 200
    assert_host_ids_in_response(response_data, [created_hosts["stale_warning"]])


def test_get_only_unknown(mq_create_hosts_in_all_states, db_create_host_in_unknown_state, api_get):
    response_status, response_data = api_get(HOST_URL, query_parameters={"staleness": "unknown"})

    assert response_status == 200
    assert_host_ids_in_response(response_data, [db_create_host_in_unknown_state])


def test_get_multiple_states(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    response_status, response_data = api_get(HOST_URL, query_parameters={"staleness": "fresh,stale"})

    assert response_status == 200
    assert_host_ids_in_response(response_data, [created_hosts["fresh"], created_hosts["stale"]])


def test_get_hosts_list_default_ignores_culled(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    response_status, response_data = api_get(HOST_URL)

    assert response_status == 200
    assert created_hosts["culled"].id not in [host["id"] for host in response_data["results"]]


def test_get_hosts_by_id_default_ignores_culled(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_hosts_url(host_list=created_hosts)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert created_hosts["culled"].id not in [host["id"] for host in response_data["results"]]


def test_tags_default_ignores_culled(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_tags_url(host_list=created_hosts)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert created_hosts["culled"].id not in tuple(response_data["results"].keys())


def test_tags_count_default_ignores_culled(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_tags_url(host_list=created_hosts, count=True)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert created_hosts["culled"].id not in tuple(response_data["results"].keys())


def test_get_system_profile_ignores_culled(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_system_profile_url(host_list=created_hosts)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert created_hosts["culled"].id not in [host["id"] for host in response_data["results"]]


def test_patch_ignores_culled(mq_create_hosts_in_all_states, api_patch):
    culled_host = mq_create_hosts_in_all_states["culled"]

    url = build_hosts_url(host_list=[culled_host])
    response_status, response_data = api_patch(url, {"display_name": "patched"})

    assert response_status == 404


def test_patch_works_on_non_culled(mq_create_hosts_in_all_states, api_patch):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_hosts_url(host_list=[fresh_host])
    response_status, response_data = api_patch(url, {"display_name": "patched"})

    assert response_status == 200


def test_patch_facts_ignores_culled(mq_create_hosts_in_all_states, api_patch):
    culled_host = mq_create_hosts_in_all_states["culled"]

    url = build_facts_url(host_list=[culled_host], namespace="ns1")
    response_status, response_data = api_patch(url, {"ARCHITECTURE": "patched"})

    assert response_status == 400


def test_patch_facts_works_on_non_culled(mq_create_hosts_in_all_states, api_patch):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_facts_url(host_list=[fresh_host], namespace="ns1")
    response_status, response_data = api_patch(url, {"ARCHITECTURE": "patched"})

    assert response_status == 200


def test_put_facts_ignores_culled(mq_create_hosts_in_all_states, api_put):
    culled_host = mq_create_hosts_in_all_states["culled"]

    url = build_facts_url(host_list=[culled_host], namespace="ns1")
    response_status, response_data = api_put(url, {"ARCHITECTURE": "patched"})

    assert response_status == 400


def test_put_facts_works_on_non_culled(mq_create_hosts_in_all_states, api_put):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_facts_url(host_list=[fresh_host], namespace="ns1")
    response_status, response_data = api_put(url, {"ARCHITECTURE": "patched"})

    assert response_status == 200


def test_delete_ignores_culled(mq_create_hosts_in_all_states, api_delete_host):
    culled_host = mq_create_hosts_in_all_states["culled"]

    response_status, response_data = api_delete_host(culled_host.id)

    assert response_status == 404


def test_delete_works_on_non_culled(mq_create_hosts_in_all_states, api_delete_host):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    response_status, response_data = api_delete_host(fresh_host.id)

    assert response_status == 200


def test_get_host_by_id_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_hosts_url(host_list=created_hosts)
    response_status, response_data = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


def test_tags_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_tags_url(host_list=created_hosts)
    response_status, response_data = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


def test_tags_count_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_tags_url(host_list=created_hosts, count=True)
    response_status, response_data = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


def test_system_profile_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_system_profile_url(host_list=created_hosts)
    response_status, response_data = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.parametrize("culling_stale_warning_offset_days", (1, 7, 12))
def test_stale_warning_timestamp(
    culling_stale_warning_offset_days, inventory_config, mq_create_or_update_host, api_get
):
    original_culling_stale_warning_offset_days = inventory_config.culling_stale_warning_offset_days
    inventory_config.culling_stale_warning_offset_days = culling_stale_warning_offset_days

    stale_timestamp = now() + timedelta(hours=1)
    host = minimal_host(stale_timestamp=stale_timestamp.isoformat())
    created_host = mq_create_or_update_host(host)

    url = build_hosts_url(created_host.id)
    response_status, response_data = api_get(url)
    assert response_status == 200

    stale_warning_timestamp = stale_timestamp + timedelta(days=culling_stale_warning_offset_days)
    assert stale_warning_timestamp.isoformat() == response_data["results"][0]["stale_warning_timestamp"]

    inventory_config.culling_stale_warning_offset_days = original_culling_stale_warning_offset_days


@pytest.mark.parametrize("culling_culled_offset_days", (8, 14, 20))
def test_culled_timestamp(culling_culled_offset_days, inventory_config, mq_create_or_update_host, api_get):
    original_culling_culled_offset_days = inventory_config.culling_culled_offset_days
    inventory_config.culling_culled_offset_days = culling_culled_offset_days

    stale_timestamp = now() + timedelta(hours=1)
    host = minimal_host(stale_timestamp=stale_timestamp.isoformat())
    created_host = mq_create_or_update_host(host)

    url = build_hosts_url(created_host.id)
    response_status, response_data = api_get(url)
    assert response_status == 200

    culled_timestamp = stale_timestamp + timedelta(days=culling_culled_offset_days)
    assert culled_timestamp.isoformat() == response_data["results"][0]["culled_timestamp"]

    inventory_config.culling_culled_offset_days = original_culling_culled_offset_days


@pytest.mark.host_reaper
def test_culled_host_is_removed(
    event_producer_mock, event_datetime_mock, db_create_host, db_get_host, inventory_config
):
    staleness_timestamps = get_staleness_timestamps()

    host = minimal_db_host(stale_timestamp=staleness_timestamps["culled"].isoformat(), reporter="some reporter")
    created_host = db_create_host(host)

    assert db_get_host(created_host.id)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    host_reaper_run(inventory_config, mock.Mock(), db.session, event_producer_mock)

    assert not db_get_host(created_host.id)

    assert_delete_event_is_valid(event_producer=event_producer_mock, host=created_host, timestamp=event_datetime_mock)


@pytest.mark.host_reaper
def test_non_culled_host_is_not_removed(
    event_producer_mock, event_datetime_mock, db_create_host, db_get_hosts, inventory_config
):
    staleness_timestamps = get_staleness_timestamps()
    created_hosts = []

    for stale_timestamp in (
        staleness_timestamps["stale_warning"],
        staleness_timestamps["stale"],
        staleness_timestamps["fresh"],
    ):
        host = minimal_db_host(stale_timestamp=stale_timestamp.isoformat(), reporter="some reporter")
        created_host = db_create_host(host)
        created_hosts.append(created_host)

    created_host_ids = [host.id for host in created_hosts]
    retrieved_hosts = db_get_hosts(created_host_ids)

    assert created_host_ids == [host.id for host in retrieved_hosts]

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    host_reaper_run(inventory_config, mock.Mock(), db.session, event_producer_mock)

    retrieved_hosts = db_get_hosts(created_host_ids)

    assert created_host_ids == [host.id for host in retrieved_hosts]
    assert event_producer_mock.event is None


@pytest.mark.host_reaper
def test_unknown_host_is_not_removed(
    event_producer_mock, db_create_host_in_unknown_state, db_get_host, inventory_config
):
    created_host = db_create_host_in_unknown_state
    retrieved_host = db_get_host(created_host.id)

    assert retrieved_host
    assert retrieved_host.stale_timestamp is None
    assert retrieved_host.reporter is None

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    host_reaper_run(inventory_config, mock.Mock(), db.session, event_producer_mock)

    assert db_get_host(created_host.id)
    assert event_producer_mock.event is None
