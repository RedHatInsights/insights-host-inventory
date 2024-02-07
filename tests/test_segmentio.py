import segment.analytics as analytics

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_resource_types_url


def test_segmentio_track_with_write_key(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"

    response_status, response_data = api_get(
        build_resource_types_url(), extra_headers={"User-Agent": "test-user-agent"}
    )

    assert_response_status(response_status, 200)

    assert "test" == mock_track.call_args_list[0][0][0]
    assert "get_resource_type_list" == mock_track.call_args_list[0][0][1]
    assert "test-user-agent" == mock_track.call_args_list[0][1]["properties"]["user_agent"]
    assert 200 == mock_track.call_args_list[0][1]["properties"]["status_code"]
    assert "basic-auth" == mock_track.call_args_list[0][1]["properties"]["auth_type"]
    assert "Insights Host Inventory API" == mock_track.call_args_list[0][1]["context"]["app"]["name"]

    assert mock_track.call_count == 1


def test_segmentio_track_without_write_key(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = ""

    response_status, response_data = api_get(build_resource_types_url())

    assert_response_status(response_status, 200)

    assert [] == mock_track.call_args_list

    assert analytics.write_key == ""
    assert mock_track.call_count == 0


def test_segmentio_track_without_user_agent(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": ""})

    assert_response_status(response_status, 200)

    assert [] == mock_track.call_args_list
    assert mock_track.call_count == 0


def test_segmentio_track_satellite(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    user_agent = "Satellite/6***.1***.5***.6***;foreman_rh_cloud/5.0.46;insights-client/3.1.8 \
    (Core 3.2.1; requests 2.6.0) Red Hat Enterprise Linux Server 7.9 (CPython 2.7.5; \
    Linux 3.10.0-1160.99.1.el7.x86_64); systemd"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": user_agent})

    assert_response_status(response_status, 200)

    assert [] == mock_track.call_args_list
    assert mock_track.call_count == 0


def test_segmentio_track_web_browser(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) \
    AppleWebKit/537.36 (KHTML, like Gecko) \
    Chrome/1***.0***.0***.0*** Safari/537.36"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": user_agent})

    assert_response_status(response_status, 200)

    assert [] == mock_track.call_args_list
    assert mock_track.call_count == 0


def test_segmentio_track_insights_client(mocker, api_get):
    mock_track = mocker.patch("api.segmentio.analytics.track")
    analytics.write_key = "test_write_key"
    user_agent = "insights-client/3.1.8 (Core 3.2.23; requests 2.6.0) \
    Red Hat Enterprise Linux Server 7.9 (CPython 2.7.5; \
    Linux 3.10.0-1160.102.1.el7.x86_64); systemd"

    response_status, response_data = api_get(build_resource_types_url(), extra_headers={"User-Agent": user_agent})

    assert_response_status(response_status, 200)

    assert [] == mock_track.call_args_list
    assert mock_track.call_count == 0
