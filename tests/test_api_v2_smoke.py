from tests.helpers.v2_api_utils import V2_BASE_URL


def test_v2_routing_does_not_crash(v2_api_get):
    response_status, _ = v2_api_get(V2_BASE_URL)
    # With paths: {} in the V2 spec, no V2 routes exist yet.
    # A non-500 response proves the V2-enabled app starts and serves requests.
    assert response_status != 500
