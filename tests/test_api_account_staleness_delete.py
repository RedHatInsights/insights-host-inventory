from tests.helpers.api_utils import assert_response_status


def test_delete_existing_account_staleness(
    db_create_account_staleness_culling, api_delete_account_staleness, db_get_account_staleness_culling
):
    saved_staleness = db_create_account_staleness_culling(
        conventional_staleness_delta=1,
        conventional_stale_warning_delta=7,
        conventional_culling_delta=14,
        immutable_staleness_delta=7,
        immutable_stale_warning_delta=120,
        immutable_culling_delta=120,
    )

    response_status, response_data = api_delete_account_staleness()
    assert_response_status(response_status, 204)

    # checking if the record was really removed
    deleted_staleness = db_get_account_staleness_culling(saved_staleness.org_id)
    assert deleted_staleness is None


def test_delete_non_existing_account_staleness(api_delete_account_staleness):
    response_status, response_data = api_delete_account_staleness()
    assert_response_status(response_status, 404)
