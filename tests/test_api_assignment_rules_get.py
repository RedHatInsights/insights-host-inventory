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