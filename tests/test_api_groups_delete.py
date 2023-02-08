from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import generate_uuid


def test_delete_non_existent_group(api_delete_group):
    group_id = generate_uuid()

    response_status, response_data = api_delete_group(group_id)

    assert_response_status(response_status, expected_status=404)


def test_delete_with_invalid_group_id(api_delete_group):
    group_id = "notauuid"

    response_status, response_data = api_delete_group(group_id)

    assert_response_status(response_status, expected_status=400)


def test_delete_group_id(db_create_group, db_get_group, api_delete_group):
    group = db_create_group("test_group")

    response_status, response_data = api_delete_group(group.id)

    assert_response_status(response_status, expected_status=200)

    assert not db_get_group(group.id)
