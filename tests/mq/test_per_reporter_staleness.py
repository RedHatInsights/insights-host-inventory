from datetime import datetime
from datetime import timedelta

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import minimal_host


def _assert_reporters(event_host, expected_reporters, expected_reporter, api_get):
    response_status, response_data = api_get(build_hosts_url(host_list_or_id=event_host.id))
    assert_response_status(response_status, 200)
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["reporter"] == expected_reporter
    for host in (event_host.data(), response_data["results"][0]):
        assert set(host["per_reporter_staleness"]) == expected_reporters
        assert all(host["per_reporter_staleness"].values())


@pytest.mark.parametrize("new_reporter", ("satellite", "discovery"))
@pytest.mark.parametrize("other_reporters", ((), ("puptoo", "rhsm-conduit", "cloud-connector", "iqe-hbi")))
def test_yupana_replacement_outputs(mq_create_or_update_host, api_get, new_reporter, other_reporters):
    host = minimal_host(reporter="yupana")
    for reporter in other_reporters:
        host.reporter = reporter
        mq_create_or_update_host(host)

    host.reporter = "yupana"
    created = mq_create_or_update_host(host)
    _assert_reporters(created, {*other_reporters, "yupana"}, "yupana", api_get)

    host.reporter = new_reporter
    updated = mq_create_or_update_host(host)
    assert updated.id == created.id
    _assert_reporters(updated, {*other_reporters, new_reporter}, new_reporter, api_get)


@pytest.mark.parametrize("reporter", ("puptoo", "rhsm-conduit", "cloud-connector", "iqe-hbi"))
def test_ordinary_reporters_preserve_yupana_outputs(mq_create_or_update_host, api_get, reporter):
    host = minimal_host(reporter="yupana")
    created = mq_create_or_update_host(host)
    _assert_reporters(created, {"yupana"}, "yupana", api_get)

    host.reporter = reporter
    updated = mq_create_or_update_host(host)
    assert updated.id == created.id
    _assert_reporters(updated, {"yupana", reporter}, reporter, api_get)


@pytest.mark.parametrize("first_reporter", ("puptoo", "rhsm-conduit", "cloud-connector"))
@pytest.mark.parametrize("second_reporter", ("satellite", "discovery"))
def test_replacement_reporters_preserve_others_outputs(
    mq_create_or_update_host, api_get, first_reporter, second_reporter
):
    host = minimal_host(reporter=first_reporter)
    created = mq_create_or_update_host(host)
    _assert_reporters(created, {first_reporter}, first_reporter, api_get)

    host.reporter = second_reporter
    updated = mq_create_or_update_host(host)
    assert updated.id == created.id
    _assert_reporters(updated, {first_reporter, second_reporter}, second_reporter, api_get)


def test_ingress_lifecycle_timestamps_are_ignored(
    api_create_staleness, mq_create_or_update_host, api_get, models_datetime_mock
):
    settings = {
        "conventional_time_to_stale": 3600,
        "conventional_time_to_stale_warning": 7200,
        "conventional_time_to_delete": 10800,
    }
    response_status, _ = api_create_staleness(settings)
    assert_response_status(response_status, 201)
    expected_offsets = {"stale_timestamp": 3600, "stale_warning_timestamp": 7200, "culled_timestamp": 10800}
    supplied = {
        field: (models_datetime_mock + timedelta(days=days)).isoformat()
        for days, field in enumerate(expected_offsets, start=1)
    }
    for system_profile in ({}, {"host_type": "edge"}):
        host = minimal_host(reporter="puptoo", system_profile=system_profile, **supplied)
        created = mq_create_or_update_host(host)
        response_status, response_data = api_get(build_hosts_url(host_list_or_id=created.id))
        assert_response_status(response_status, 200)
        assert len(response_data["results"]) == 1
        for output in (created.data(), response_data["results"][0]):
            check_in = datetime.fromisoformat(output["last_check_in"])
            assert check_in == models_datetime_mock
            for field, seconds in expected_offsets.items():
                assert datetime.fromisoformat(output[field]) == check_in + timedelta(seconds=seconds)
                assert output[field] != supplied[field]
