import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import ASSIGNMENT_RULE_URL
from tests.helpers.api_utils import build_assignment_rules_url


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

    _ = db_create_assignment_rule("good-name", group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]
    url_with_name = ASSIGNMENT_RULE_URL + "?name=" + rule_1["name"]

    _, new_response_data = api_get(url_with_name)
    rule_2 = new_response_data["results"][0]

    assert rule_1 == rule_2


def test_get_assignment_rule_with_bad_name(db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    _ = [db_create_assignment_rule(f"assignment {idx}", group.id, filter, True).id for idx in range(3)]

    response_status, response_data = api_get(build_assignment_rules_url())
    assert response_status == 200
    assert response_data["total"] == 3
    assert response_data["count"] == 3
    assert len(response_data["results"]) == 3

    url_with_bad_name = ASSIGNMENT_RULE_URL + "?name=bad_name"

    new_response_status, new_response_data = api_get(url_with_bad_name)
    assert new_response_status == 200
    assert new_response_data["total"] == 0
    assert new_response_data["count"] == 0
    assert new_response_data["results"] == []


@pytest.mark.parametrize(
    "order_by, order_how",
    (
        ("org_id", "ASC"),
        ("org_id", "DESC"),
        ("account", "ASC"),
        ("account", "DESC"),
        ("name", "DESC"),
        ("name", "ASC"),
        ("group_id", "DESC"),
        ("group_id", "ASC"),
    ),
)
def test_order_by_and_order_how(db_create_assignment_rule, db_create_group, api_get, order_by, order_how):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    _ = db_create_assignment_rule(order_by, group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]
    url_with_name = ASSIGNMENT_RULE_URL + f"?order_by={order_by}&order_how={order_how}"

    _, new_response_data = api_get(url_with_name)
    rule_2 = new_response_data["results"][0]

    assert rule_1 == rule_2


@pytest.mark.parametrize(
    "order_by, order_how",
    (
        ("org_id", "BASC"),  # Bad ascending order value for order_by
        ("org_id", "BDESC"),  # Bad descending order value for order_how
        ("bad_name", "ASC"),  # Bad order_by value
    ),
)
def test_wrong_order_by_and_order_how(db_create_assignment_rule, db_create_group, api_get, order_by, order_how):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    _ = db_create_assignment_rule(order_by, group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]

    # verify the rule was created successfully
    assert order_by == rule_1["name"]

    url_with_name = ASSIGNMENT_RULE_URL + f"?order_by={order_by}&order_how={order_how}"

    new_response_status, new_response_data = api_get(url_with_name)
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

    _ = db_create_assignment_rule("test_assignment_rule", group.id, filter, True)
    _, response_data = api_get(build_assignment_rules_url())

    rule_1 = response_data["results"][0]

    # verify the rule was created successfully
    assert "test_assignment_rule" == rule_1["name"]

    url_with_name = ASSIGNMENT_RULE_URL + f"?page={page}&per_page={per_page}"

    new_response_status, new_response_data = api_get(url_with_name)
    assert new_response_status == 200
    assert new_response_data["page"] == page
    assert new_response_data["per_page"] == per_page
