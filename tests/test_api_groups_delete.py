from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import generate_uuid


def test_delete_non_existent_group(api_delete_groups):
    group_id = generate_uuid()

    response_status, response_data = api_delete_groups([group_id])

    assert_response_status(response_status, expected_status=404)


def test_delete_with_invalid_group_id(api_delete_groups):
    group_id = "notauuid"

    response_status, response_data = api_delete_groups(group_id)

    assert_response_status(response_status, expected_status=400)


def test_delete_group_ids(db_create_group, db_get_group, api_delete_groups):
    group_list = [db_create_group(f"test_group{g_index}") for g_index in range(3)]

    response_status, response_data = api_delete_groups([group.id for group in group_list])

    assert_response_status(response_status, expected_status=200)

    for group in group_list:
        assert not db_get_group(group.id)
