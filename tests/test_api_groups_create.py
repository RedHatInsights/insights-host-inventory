from tests.helpers.api_utils import assert_response_status


def test_create_group_without_hosts(api_create_group, db_get_hosts_for_group):
    group_data = {"name": "my_awesome_group", "host_ids": []}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)


def test_create_group_with_hosts(db_create_host, api_create_group):
    host1 = db_create_host()
    host2 = db_create_host()

    group_data = {"name": "my_awesome_group", "host_ids": [str(host1.id), str(host2.id)]}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)
    # check if hosts were associated with created group


def test_create_invalid_group(api_create_group):
    group_data = {"name": "", "host_ids": []}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)


def test_create_group_invalid_host_ids(api_create_group):
    group_data = {"name": "my_awesome_group", "host_ids": ["notauuid"]}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)

    # check for something indicating that the host wasn't added
