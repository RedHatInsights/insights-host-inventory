from sqlalchemy import func

from app import db
from app.auth import get_current_identity
from app.models import AssignmentRule
from app.serialization import serialize_assignment_rule


def get_assignment_rules_list_db(filters, page, per_page, param_order_by, param_order_how, rbac_filter):
    if rbac_filter and "assignment_rules" in rbac_filter:
        filters += (AssignmentRule.id.in_(rbac_filter["assignment_rules"]),)

    assingnment_rules_list = (
        AssignmentRule.query
        .offset(page - 1)
        .limit(per_page)
        .all()
    )

    # Get the total number of assignment-rules that would be returned using just the filters
    total = db.session.query(func.count(AssignmentRule.id)).filter(*filters).scalar()

    return assingnment_rules_list, total


def get_filtered_assignment_rule_list_db(rule_name, page, per_page, order_by, order_how, rbac_filter):
    filters = (AssignmentRule.org_id == get_current_identity().org_id,)
    if rule_name:
        filters += (func.lower(AssignmentRule.name).contains(func.lower(rule_name)),)
    return get_assignment_rules_list_db(filters, page, per_page, order_by, order_how, rbac_filter)


def build_paginated_assignmentrule_list_response(total, page, per_page, rules_list):
    rule_list_json = [serialize_assignment_rule(rule) for rule in rules_list]
    return {
        "total": total,
        "count": len(rule_list_json),
        "page": page,
        "per_page": per_page,
        "results": rule_list_json,
    }
