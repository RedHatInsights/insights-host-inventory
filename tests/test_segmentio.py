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
