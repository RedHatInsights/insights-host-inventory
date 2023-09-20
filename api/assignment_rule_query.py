from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app import db
from app.auth import get_current_identity
from app.logging import get_logger
from app.models import AssignmentRule
from app.serialization import serialize_assignment_rule


logger = get_logger(__name__)

ASSIGNMENT_RULES_ORDER_BY_MAPPING = {
    "org_id": AssignmentRule.org_id,
    "account": AssignmentRule.account,
    "name": AssignmentRule.name,
    "group_id": AssignmentRule.group_id,
}

ASSIGNMENT_RULES_ORDER_HOW_BY_FIELD = {"org_id": asc, "account": desc, "name": asc, "group_id": asc}
ASSIGNMENT_RULES_ORDER_HOW = {"asc": asc, "desc": desc}


def get_assignment_rules_list_db(filters, page, per_page, param_order_by, param_order_how, rbac_filter):
    # Apply RBAC group ID filter, if provided
    if rbac_filter and "groups" in rbac_filter:
        filters += (AssignmentRule.group_id.in_(rbac_filter["groups"]),)

    order_by_str = param_order_by or "name"
    order_by = ASSIGNMENT_RULES_ORDER_BY_MAPPING[order_by_str]
    order_how_func = (
        ASSIGNMENT_RULES_ORDER_HOW[param_order_how.lower()]
        if param_order_how
        else ASSIGNMENT_RULES_ORDER_HOW_BY_FIELD[order_by_str]
    )

    assignment_rules_list = (
        AssignmentRule.query.filter(*filters).order_by(order_how_func(order_by)).offset(page - 1).limit(per_page).all()
    )

    # Get the total number of assignment-rules that would be returned using just the filters
    total = db.session.query(func.count(AssignmentRule.id)).filter(*filters).scalar()

    return assignment_rules_list, total


def get_assignment_rules_list_by_id_list_db(assignment_rule_id_list, page, per_page, order_by, order_how, rbac_filter):
    filters = (
        AssignmentRule.org_id == get_current_identity().org_id,
        AssignmentRule.id.in_(assignment_rule_id_list),
    )
    return get_assignment_rules_list_db(filters, page, per_page, order_by, order_how, rbac_filter)


def get_filtered_assignment_rule_list_db(rule_name, page, per_page, order_by, order_how, rbac_filter):
    filters = (AssignmentRule.org_id == get_current_identity().org_id,)
    if rule_name:
        filters += (func.lower(AssignmentRule.name).contains(func.lower(rule_name)),)
    return get_assignment_rules_list_db(filters, page, per_page, order_by, order_how, rbac_filter)


def build_paginated_assignment_rule_list_response(total, page, per_page, rules_list):
    rule_list_json = [serialize_assignment_rule(rule) for rule in rules_list]
    return {
        "total": total,
        "count": len(rule_list_json),
        "page": page,
        "per_page": per_page,
        "results": rule_list_json,
    }
