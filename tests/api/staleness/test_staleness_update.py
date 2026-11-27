import pytest

from tests.helpers.api_utils import _INPUT_DATA as _DEFAULT_STALENESS_TRIPLE
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import run_rbac_test
from tests.helpers.staleness_test_constants import AT_EXACTLY_ONE_HOUR
from tests.helpers.staleness_test_constants import CUSTOM_STALENESS
from tests.helpers.staleness_test_constants import JUST_UNDER_ONE_HOUR
from tests.helpers.staleness_test_constants import assert_staleness_row_matches_triple
from tests.helpers.test_utils import USER_IDENTITY

_INPUT_DATA = {"conventional_time_to_stale": 99}


def test_update_existing_record(api_create_staleness, api_patch, api_get, db_get_staleness_culling):
    response_status, _ = api_create_staleness(CUSTOM_STALENESS)
    assert_response_status(response_status, 201)
    url = build_staleness_url()
    expected = dict(CUSTOM_STALENESS)
    # One/two/all-field updates, then the inclusive minimum and maximum.
    for payload in (
        _INPUT_DATA,
        {"conventional_time_to_stale": 100, "conventional_time_to_stale_warning": 200},
        {
            "conventional_time_to_stale": 10,
            "conventional_time_to_stale_warning": 20,
            "conventional_time_to_delete": 30,
        },
        {"conventional_time_to_stale": 1},
        {"conventional_time_to_delete": 63072000},
    ):
        response_status, response_data = api_patch(url, host_data=payload)
        assert_response_status(response_status, 200)
        expected.update(payload)
        assert {field: response_data[field] for field in expected} == expected
        assert_staleness_row_matches_triple(db_get_staleness_culling(response_data["org_id"]), expected)

        response_status, response_data = api_get(url)
        assert_response_status(response_status, 200)
        assert {field: response_data[field] for field in expected} == expected


def test_update_non_existing_record(api_patch):
    url = build_staleness_url()
    response_status, response_data = api_patch(url, host_data=_INPUT_DATA)
    assert_response_status(response_status, 404)
    assert "does not exist" in response_data["detail"]
    assert USER_IDENTITY["org_id"] in response_data["detail"]


def test_update_with_wrong_data(api_patch):
    url = build_staleness_url()
    response_status, _ = api_patch(url, host_data={"conventional_time_to_stale": "9999"})
    assert_response_status(response_status, 400)


def test_update_staleness_invalid_values(api_patch, subtests):
    """Validation must fail before a missing custom record can return 404."""
    limits = {
        "conventional_time_to_stale": 604800,
        "conventional_time_to_stale_warning": 15552000,
        "conventional_time_to_delete": 63072000,
    }
    for field, maximum in limits.items():
        for value in (0, "abc", -1, 3.5, [], {}, maximum + 1):
            with subtests.test(field=field, value=value):
                response_status, response_data = api_patch(build_staleness_url(), host_data={field: value})
                assert_response_status(response_status, 400)
                detail = response_data["detail"]
                assert field in detail
                if not isinstance(value, int):
                    assert "integer" in detail
                elif value <= 0:
                    assert "minimum" in detail
                else:
                    assert str(maximum) in detail


def test_update_staleness_invalid_ordering(api_patch, subtests):
    fields = ("conventional_time_to_stale", "conventional_time_to_stale_warning", "conventional_time_to_delete")
    payloads = [
        {fields[0]: 604800, fields[1]: 1},
        {fields[2]: 1},
        dict(zip(fields, (1, 3, 2), strict=True)),
        dict(zip(fields, (2, 1, 3), strict=True)),
        dict(zip(fields, (2, 3, 1), strict=True)),
    ]
    for payload in payloads:
        with subtests.test(payload=payload):
            response_status, response_data = api_patch(build_staleness_url(), host_data=payload)
            assert_response_status(response_status, 400)
            assert "must be lower than" in response_data["detail"]
            assert "conventional_time_to_" in response_data["detail"]


def test_update_staleness_with_unknown_field(api_patch, api_get, db_create_staleness_culling):
    """Unknown input is rejected, not silently accepted; check the unfiltered GET response."""
    db_create_staleness_culling(**CUSTOM_STALENESS)
    response_status, response_data = api_patch(
        build_staleness_url(), host_data={"conventional_time_to_stale": 86400, "bad_field": 86400}
    )
    assert_response_status(response_status, 400)
    assert "bad_field" in response_data["detail"]
    assert "unknown" in response_data["detail"].lower()

    response_status, response_data = api_get(build_staleness_url())
    assert_response_status(response_status, 200)
    assert "bad_field" not in response_data
    assert {field: response_data[field] for field in CUSTOM_STALENESS} == CUSTOM_STALENESS


@pytest.mark.usefixtures("enable_rbac")
def test_update_staleness_rbac_allowed(subtests, mocker, api_patch, db_create_staleness_culling):
    db_create_staleness_culling(conventional_time_to_stale=1)
    url = build_staleness_url()
    run_rbac_test(subtests, mocker, api_patch, STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES, 200, [url, _INPUT_DATA])


@pytest.mark.usefixtures("enable_rbac")
def test_update_staleness_rbac_denied(subtests, mocker, api_patch, db_create_staleness_culling):
    db_create_staleness_culling(conventional_time_to_stale=1)
    url = build_staleness_url()
    run_rbac_test(subtests, mocker, api_patch, STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES, 403, [url, _INPUT_DATA])


def test_patch_staleness_at_defaults_without_custom_returns_404(api_patch):
    """No custom row: PATCH does not update anything and returns 404 (even for default-equivalent payload)."""
    response_status, _ = api_patch(build_staleness_url(), host_data=_DEFAULT_STALENESS_TRIPLE)
    assert_response_status(response_status, 404)


def test_patch_staleness_just_under_one_hour_without_custom_returns_404(api_patch, db_get_staleness_culling):
    """Near-default-equivalent payload does not turn PATCH into 200 when there is no custom row."""
    response_status, _ = api_patch(build_staleness_url(), host_data=JUST_UNDER_ONE_HOUR)
    assert_response_status(response_status, 404)
    assert db_get_staleness_culling(USER_IDENTITY["org_id"]) is None


def test_patch_staleness_just_under_one_hour_deletes_custom(
    api_patch, db_create_staleness_culling, db_get_staleness_culling
):
    """All three fields +3599s from defaults (strictly < 1h) removes the custom row."""
    db_create_staleness_culling(**CUSTOM_STALENESS)
    response_status, response_data = api_patch(build_staleness_url(), host_data=JUST_UNDER_ONE_HOUR)
    assert_response_status(response_status, 200)
    assert response_data["id"] == "system_default"
    assert db_get_staleness_culling(response_data["org_id"]) is None


def test_patch_staleness_at_exactly_one_hour_keeps_custom(
    api_patch, db_create_staleness_culling, db_get_staleness_culling
):
    """All three fields exactly +3600s from defaults should keep a custom row (not default-equivalent)."""
    db_create_staleness_culling(**CUSTOM_STALENESS)
    response_status, response_data = api_patch(build_staleness_url(), host_data=AT_EXACTLY_ONE_HOUR)
    assert_response_status(response_status, 200)
    assert response_data["id"] != "system_default"
    row = db_get_staleness_culling(response_data["org_id"])
    assert row is not None
    assert_staleness_row_matches_triple(row, AT_EXACTLY_ONE_HOUR)
