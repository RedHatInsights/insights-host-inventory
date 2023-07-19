from tests.helpers.api_utils import assert_response_status
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
