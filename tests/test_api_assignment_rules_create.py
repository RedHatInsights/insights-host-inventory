import pytest

from tests.helpers.api_utils import GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_assign_rule_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import generate_uuid


def test_create_assignment_rule(api_create_assign_rule, db_create_group):
    group = db_create_group("my_group")

    assign_rule_data = {
        "name": "myRule1",
        "description": "something",
        "group_id": str(group.id),
        "filter": {
            "AND": [{"tags": {"eq": "satellite/content_view=RHEL8"}}, {"operating_system": {"matches": "8.*"}}]
        },
        "enabled": True,
    }

    response_status, response_data = api_create_assign_rule(assign_rule_data)

    assert_response_status(response_status, expected_status=201)
    assert_assign_rule_response(response_data, assign_rule_data)


def test_create_assignemnt_rule_bad_request(subtests, api_create_assign_rule, db_create_group):
    required_fields = ["name", "group_id", "filter", "enabled"]
    group = db_create_group("my_group")

    for field in required_fields:
        assign_rule_data = {
            "name": "coolName",
            "description": "something",
            "group_id": str(group.id),
            "filter": {
                "AND": [{"tags": {"eq": "satellite/content_view=RHEL8"}}, {"operating_system": {"matches": "8.*"}}]
            },
            "enabled": True,
        }
        del assign_rule_data[field]
        with subtests.test():
            response_status, response_data = api_create_assign_rule(assign_rule_data)
            assert_response_status(response_status, expected_status=400)
            assert f"{field}" in response_data["detail"]


def test_create_assignment_rule_group_not_exists(api_create_assign_rule):
    assign_rule_data = {
        "name": "myRule1",
        "description": "something",
        "group_id": str(generate_uuid()),
        "filter": {
            "AND": [{"tags": {"eq": "satellite/content_view=RHEL8"}}, {"operating_system": {"matches": "8.*"}}]
        },
        "enabled": True,
    }

    response_status, response_data = api_create_assign_rule(assign_rule_data)
    assert_response_status(response_status, expected_status=400)
    assert assign_rule_data["group_id"] in response_data["detail"]


@pytest.mark.skip(reason="Need to validate why the test is creating duplicates in the DB")
def test_create_assignemnt_rule_same_name(api_create_assign_rule, db_create_group):
    group = db_create_group("my_group")
    assign_rule_data = {
        "name": "myRule1",
        "description": "something",
        "group_id": str(group.id),
        "filter": {
            "AND": [{"tags": {"eq": "satellite/content_view=RHEL8"}}, {"operating_system": {"matches": "8.*"}}]
        },
        "enabled": True,
    }
    response_status, _ = api_create_assign_rule(assign_rule_data)
    response_status, response_data = api_create_assign_rule(assign_rule_data)
    assert_response_status(response_status, expected_status=400)
    assert assign_rule_data["name"] in response_data["detail"]


@pytest.mark.skip(reason="Need to validate why the test is creating duplicates in the DB")
def test_create_assignemnt_rule_same_group(api_create_assign_rule, db_create_group):
    group = db_create_group("my_group")
    assign_rule_data = {
        "name": "myRule1",
        "description": "something",
        "group_id": str(group.id),
        "filter": {
            "AND": [{"tags": {"eq": "satellite/content_view=RHEL8"}}, {"operating_system": {"matches": "8.*"}}]
        },
        "enabled": True,
    }

    assign_rule_same_group = assign_rule_data.copy()
    assign_rule_same_group["name"] = "myRule2"

    response_status, _ = api_create_assign_rule(assign_rule_data)
    response_status, response_data = api_create_assign_rule(assign_rule_same_group)
    assert_response_status(response_status, expected_status=400)
    assert group in response_data["detail"]


def test_create_assignment_rule_RBAC_denied(subtests, mocker, api_create_assign_rule, db_create_group, _enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    group = db_create_group("my_group")

    assign_rule_data = {
        "name": "myRule1",
        "description": "something",
        "group_id": str(group.id),
        "filter": {
            "AND": [{"tags": {"eq": "satellite/content_view=RHEL8"}}, {"operating_system": {"matches": "8.*"}}]
        },
        "enabled": True,
    }

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_create_assign_rule(assign_rule_data)

            assert_response_status(response_status, 403)
