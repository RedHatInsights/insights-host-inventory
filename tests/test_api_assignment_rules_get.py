# import uuid
# import pytest
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_assignment_rules_url

# from tests.helpers.api_utils import ASSIGNMENT_RULE_URL


def test_basic_assignment_rule_query(db_create_assignment_rule, db_create_group, api_get):
    group = db_create_group("TestGroup")
    filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

    assignment_rule_id_list = [
        str(db_create_assignment_rule(f"assignment {idx}", group.id, filter, True).id) for idx in range(3)
    ]
    response_status, response_data = api_get(build_assignment_rules_url())

    assert_response_status(response_status, 200)

    # assert response_data["detail"]["total"] == 3
    # assert response_data["detail"]["count"] == 3
    # for assignment_rule_result in response_data["detail"]["results"]:
    #     assert assignment_rule_result["id"] in assignment_rule_id_list

    assert response_data["total"] == 3
    assert response_data["count"] == 3
    for assignment_rule_result in response_data["results"]:
        assert assignment_rule_result["id"] in assignment_rule_id_list


# @pytest.mark.parametrize(
#     "num_rules",
#     [1, 3, 5],
# )
# def test_assignment_rule_id_list_filter(num_rules, db_create_assignment_rule, db_create_group, api_get):
#     group = db_create_group("TestGroup")
#     filter = {"AND": [{"fqdn": {"eq": "foo.bar.com"}}]}

#     assignment_rule_id_list = [
#         str(db_create_assignment_rule(f"assignment {idx}", group.id, filter).id) for idx in range(num_rules)
#     ]
#     # Create extra rules to filter out
#     for idx in range(10):
#         db_create_assignment_rule(f"extraRule_{idx}", group.id, filter)

#     url = ASSIGNMENT_RULE_URL + "/" + ",".join(assignment_rule_id_list)
#     response_status, response_data = api_get(url)

#     assert response_status == 200
#     assert response_data["total"] == num_rules
#     assert response_data["count"] == num_rules
#     assert len(response_data["results"]) == num_rules
#     for rule_result in response_data["results"]:
#         assert rule_result["id"] in assignment_rule_id_list
