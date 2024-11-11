import os
from importlib import reload
from unittest import mock

import segment.analytics as analytics

import api.segmentio
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_resource_types_url


def test_segmentio_track_with_write_key(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"

    response_status, response_data = api_get(
        build_resource_types_url(), extra_headers={"User-Agent": "test-user-agent"}
    )

    assert_response_status(response_status, 200)

    assert mock_track.call_args_list[0][0][0] == "test"
    assert mock_track.call_args_list[0][0][1] == "get_resource_type_list"
    assert mock_track.call_args_list[0][1]["properties"]["user_agent"] == "test-user-agent"
    assert mock_track.call_args_list[0][1]["properties"]["status_code"] == 200
    assert mock_track.call_args_list[0][1]["properties"]["auth_type"] == "basic-auth"
    assert mock_track.call_args_list[0][1]["context"]["app"]["name"] == "Insights Host Inventory API"

    assert mock_track.call_count == 1


def test_segmentio_track_without_write_key(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = ""

    response_status, response_data = api_get(build_resource_types_url())

    assert_response_status(response_status, 200)

    assert mock_track.call_args_list == []

    assert analytics.write_key == ""
    assert mock_track.call_count == 0


def test_segmentio_track_without_user_agent(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": ""})

    assert_response_status(response_status, 200)

    assert mock_track.call_args_list == []
    assert mock_track.call_count == 0


def test_segmentio_track_satellite(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    user_agent = "Satellite/6***.1***.5***.6***;foreman_rh_cloud/5.0.46;insights-client/3.1.8 \
    (Core 3.2.1; requests 2.6.0) Red Hat Enterprise Linux Server 7.9 (CPython 2.7.5; \
    Linux 3.10.0-1160.99.1.el7.x86_64); systemd"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": user_agent})

    assert_response_status(response_status, 200)

    assert mock_track.call_args_list == []
    assert mock_track.call_count == 0


def test_segmentio_track_web_browser(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) \
    AppleWebKit/537.36 (KHTML, like Gecko) \
    Chrome/1***.0***.0***.0*** Safari/537.36"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": user_agent})

    assert_response_status(response_status, 200)

    assert mock_track.call_args_list == []
    assert mock_track.call_count == 0


def test_segmentio_track_insights_client(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    user_agent = "insights-client/3.1.8 (Core 3.2.23; requests 2.6.0) \
    Red Hat Enterprise Linux Server 7.9 (CPython 2.7.5; \
    Linux 3.10.0-1160.102.1.el7.x86_64); systemd"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": user_agent})

    assert_response_status(response_status, 200)

    assert mock_track.call_args_list == []
    assert mock_track.call_count == 0


def test_segmentio_rate_limit(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    max_calls = 4

    #
    # Test calls that don't exceed the limit.
    #
    for _ in range(max_calls * 2):
        response_status, response_data = api_get(
            build_resource_types_url(), extra_headers={"User-Agent": "test-user-agent"}
        )
        assert_response_status(response_status, 200)

    #
    # All the calls should have been made.
    #
    assert mock_track.call_count == max_calls * 2

    #
    # Lower the maximum call limit.
    #
    with mock.patch.dict(os.environ, {"SEGMENTIO_LIMIT_CALLS": str(max_calls)}):
        reload(api.segmentio)
        reload(api)

    #
    # Test calls that do exceed the limit.
    #
    mock_track.call_count = 0
    for _ in range(max_calls * 2):
        response_status, response_data = api_get(
            build_resource_types_url(), extra_headers={"User-Agent": "test-user-agent"}
        )
        assert_response_status(response_status, 200)

    #
    # Only max_calls calls should have been made.
    #
    assert mock_track.call_count == max_calls
