from datetime import datetime
from datetime import timedelta

import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.staleness_test_constants import CUSTOM_STALENESS
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


@pytest.mark.usefixtures("models_datetime_mock")
def test_maximum_staleness_host_filters(api_create_staleness, api_get, mq_create_or_update_host):
    settings = {
        "conventional_time_to_stale": 604800,
        "conventional_time_to_stale_warning": 15552000,
        "conventional_time_to_delete": 63072000,
    }
    response_status, response_data = api_create_staleness(settings)
    assert_response_status(response_status, 201)
    assert {field: response_data[field] for field in settings} == settings
    response_status, response_data = api_get(build_staleness_url())
    assert_response_status(response_status, 200)
    assert {field: response_data[field] for field in settings} == settings

    mq_create_or_update_host(minimal_host())
    for query in ("", "?staleness=fresh", "?staleness=stale", "?staleness=stale_warning"):
        response_status, _ = api_get(build_hosts_url(query=query))
        assert_response_status(response_status, 200)


def test_host_patch_does_not_rescue_old_check_in(
    db_create_host, api_patch, api_get, api_create_staleness, mocker, event_producer_mock
):
    current_time = now()
    old_check_in = current_time - timedelta(days=1)
    clock = mocker.patch("app.models.utils.datetime", **{"now.return_value": old_check_in})
    patched, untouched = db_create_host(), db_create_host()
    old_ids = [str(patched.id), str(untouched.id)]
    clock.now.return_value = current_time

    response_status, _ = api_patch(
        build_hosts_url(host_list_or_id=old_ids[0]), host_data={"display_name": "recently patched"}
    )
    assert_response_status(response_status, 200)
    assert len(event_producer_mock.events) == 1
    response_status, response_data = api_get(build_hosts_url(host_list_or_id=old_ids))
    assert_response_status(response_status, 200)
    assert {host["id"] for host in response_data["results"]} == set(old_ids)
    assert all(datetime.fromisoformat(host["last_check_in"]) == old_check_in for host in response_data["results"])
    output = next(host for host in response_data["results"] if host["id"] == old_ids[0])
    assert output["display_name"] == "recently patched"
    assert datetime.fromisoformat(output["updated"]) == current_time

    response_status, _ = api_create_staleness(
        {
            "conventional_time_to_stale": 3600,
            "conventional_time_to_stale_warning": 7200,
            "conventional_time_to_delete": 10800,
        }
    )
    assert_response_status(response_status, 201)
    fresh_id = str(db_create_host().id)
    response_status, response_data = api_get(build_hosts_url())
    assert_response_status(response_status, 200)
    assert {host["id"] for host in response_data["results"]} == {fresh_id}


def test_staleness_mutations_do_not_emit_host_events(
    mq_create_or_update_host, event_producer_mock, api_create_staleness, api_patch, api_delete_staleness, mocker
):
    for system_profile in ({}, {"host_type": "edge"}):
        mq_create_or_update_host(minimal_host(system_profile=system_profile))
    write_event = mocker.spy(event_producer_mock, "write_event")

    response_status, _ = api_create_staleness(CUSTOM_STALENESS)
    assert_response_status(response_status, 201)
    write_event.assert_not_called()

    response_status, _ = api_patch(
        build_staleness_url(),
        host_data={
            "conventional_time_to_stale": 3600,
            "conventional_time_to_stale_warning": 7200,
            "conventional_time_to_delete": 10800,
        },
    )
    assert_response_status(response_status, 200)
    write_event.assert_not_called()

    response_status, _ = api_delete_staleness()
    assert_response_status(response_status, 204)
    write_event.assert_not_called()
