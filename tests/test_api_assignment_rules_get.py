import pytest

from tests.helpers.api_utils import ASSIGNMENT_RULE_URL
from tests.helpers.api_utils import GROUP_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_assignment_rules_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import generate_uuid


def test_basic_assignment_rule_query(db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    assignment_rule_id_list = [
        str(db_create_assignment_rule(f"assignment {idx}", group.id, filter, True).id) for idx in range(3)
    ]

    response_status, response_data = api_get(build_assignment_rules_url())

    assert_response_status(response_status, 200)
    assert response_data["total"] == 3
    assert response_data["count"] == 3
    for assignment_rule_result in response_data["results"]:
        assert assignment_rule_result["id"] in assignment_rule_id_list


def test_get_assignment_rule_by_name(db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    db_create_assignment_rule("good-name", group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]
    query = "?name=" + rule_1["name"]

    _, new_response_data = api_get(build_assignment_rules_url(query=query))
    rule_2 = new_response_data["results"][0]

    assert rule_1 == rule_2


def test_get_assignment_rule_not_found(db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    [db_create_assignment_rule(f"assignment {idx}", group.id, filter, True).id for idx in range(3)]

    response_status, response_data = api_get(build_assignment_rules_url())
    assert response_status == 200
    assert response_data["total"] == 3
    assert response_data["count"] == 3
    assert len(response_data["results"]) == 3

    bad_query = "?name=bad_name"

    new_response_status, new_response_data = api_get(build_assignment_rules_url(query=bad_query))
    assert new_response_status == 200
    assert new_response_data["total"] == 0
    assert new_response_data["count"] == 0
    assert new_response_data["results"] == []


@pytest.mark.parametrize(
    "order_by, order_how",
    (
        ("name", "DESC"),
        ("name", "ASC"),
    ),
)
def test_order_by_and_order_how(db_create_assignment_rule, db_create_group, api_get, order_by, order_how):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    [db_create_assignment_rule(f"assignment {idx}", group.id, filter, True) for idx in range(3)]

    _, response_data = api_get(build_assignment_rules_url())
    assert len(response_data["results"]) == 3

    url_with_name = ASSIGNMENT_RULE_URL + f"?order_by={order_by}&order_how={order_how}"

    _, new_response_data = api_get(url_with_name)
    assert len(new_response_data["results"]) == 3

    if order_how == "ASC":
        assert response_data["results"][0]["name"] == new_response_data["results"][0]["name"]
    if order_how == "DESC":
        assert response_data["results"][0]["name"] == new_response_data["results"][2]["name"]


@pytest.mark.parametrize(
    "order_by, order_how",
    (
        ("name", "BDESC"),  # Bad descending order value for order_how
        ("bad_name", "ASC"),  # Bad order_by value
    ),
)
def test_wrong_order_by_and_order_how(db_create_assignment_rule, db_create_group, api_get, order_by, order_how):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    db_create_assignment_rule(order_by, group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]

    # verify the rule was created successfully
    assert order_by == rule_1["name"]

    query = f"?order_by={order_by}&order_how={order_how}"

    new_response_status, new_response_data = api_get(build_assignment_rules_url(query=query))
    assert new_response_status == 400
    assert "Failed validating" in new_response_data["detail"]


@pytest.mark.parametrize(
    "page, per_page",
    (
        (2, 100),
        (10000, 10),  # using some random numbers
    ),
)
def test_page_and_page_number(db_create_assignment_rule, db_create_group, api_get, page, per_page):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    db_create_assignment_rule("test_assignment_rule", group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]

    # verify the rule was created successfully
    assert rule_1["name"] == "test_assignment_rule"

    query = f"?page={page}&per_page={per_page}"

    new_response_status, new_response_data = api_get(build_assignment_rules_url(query=query))
    assert new_response_status == 200
    assert new_response_data["page"] == page
    assert new_response_data["per_page"] == per_page


@pytest.mark.parametrize(
    "num_rules",
    [1, 3, 5],
)
def test_assignment_rule_id_list_filter(num_rules, db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    assignment_rule_id_list = [
        str(db_create_assignment_rule(f"assignment {idx}", group.id, filter, True).id) for idx in range(num_rules)
    ]
    # Create extra rules to filter out
    for idx in range(10):
        db_create_assignment_rule(f"extraRule_{idx}", group.id, filter, True)

    response_status, response_data = api_get(
        build_assignment_rules_url(assignment_rules_id_list=assignment_rule_id_list)
    )

    assert response_status == 200
    assert response_data["total"] == num_rules
    assert response_data["count"] == num_rules
    assert len(response_data["results"]) == num_rules
    for rule_result in response_data["results"]:
        assert rule_result["id"] in assignment_rule_id_list


@pytest.mark.parametrize(
    "num_rules",
    [0, 1, 3, 5],
)
def test_assignment_rule_id_list_bad_id(num_rules, db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    for idx in range(num_rules):
        db_create_assignment_rule(f"assignment {idx}", group.id, filter, True)

    id = str(generate_uuid())
    response_status, response_data = api_get(build_assignment_rules_url(assignment_rules_id_list=id))

    assert response_status == 200
    assert response_data["total"] == 0
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0


def test_get_assignment_rule_id_list_RBAC_denied(subtests, mocker, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Assignment rules get, requires group read.
    for response_file in GROUP_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            id = str(generate_uuid())
            response_status, _ = api_get(build_assignment_rules_url(assignment_rules_id_list=id))

            assert_response_status(response_status, 403)


def test_get_assignment_rules_RBAC_denied_specific_groups(
    mocker, db_create_group, db_create_assignment_rule, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(2)]
    filter_list = [{"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}, {"AND": [{"fqdn": {"eq": "boo.bar.com"}}]}]

    # Create assignment rules and assign them to each group
    [db_create_assignment_rule(f"assignment {idx}", group_id_list[idx], filter_list[idx], True).id for idx in range(2)]

    # Only grant read permission to one group in the list
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [group_id_list[0]]

    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, response_data = api_get(build_assignment_rules_url())

    assert response_status == 200
    assert response_data["total"] == 1
    assert len(response_data["results"]) == 1
