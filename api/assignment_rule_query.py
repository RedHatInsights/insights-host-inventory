from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app import db
from app.auth import get_current_identity
from app.logging import get_logger
from app.models import AssignmentRule
from app.serialization import serialize_assignment_rule
from lib.db import session_guard

logger = get_logger(__name__)

ASSIGNMENT_RULES_ORDER_BY_MAPPING = {
    "org_id": AssignmentRule.org_id,
    "account": AssignmentRule.account,
    "name": AssignmentRule.name,
    "group_id": AssignmentRule.group_id,
}

ASSIGNMENT_RULES_ORDER_HOW_MAPPING = {"org_id": asc, "account": desc, "name": asc, "group_id": asc}


def get_assignment_rules_list_db(filters, page, per_page, param_order_by, param_order_how, rbac_filter):
    if rbac_filter and "assignment_rules" in rbac_filter:
        filters += (AssignmentRule.id.in_(rbac_filter["assignment_rules"]),)

    order_by_str = param_order_by or "name"
    order_by = ASSIGNMENT_RULES_ORDER_BY_MAPPING[order_by_str]
    order_how_func = (
        ASSIGNMENT_RULES_ORDER_HOW_MAPPING[param_order_how.lower()]
        if param_order_how
        else ASSIGNMENT_RULES_ORDER_HOW_MAPPING[order_by_str]
    )

    assingnment_rules_list = (
        AssignmentRule.query.filter(*filters).order_by(order_how_func(order_by)).offset(page - 1).limit(per_page).all()
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


def add_assignment_rule(assign_rule_data) -> AssignmentRule:
    logger.debug(f"Creating assignment rule: {assign_rule_data}")
    org_id = get_current_identity().org_id
    account = get_current_identity().account_number
    assign_rule_name = assign_rule_data.get("name")
    filter = assign_rule_data.get("filter", {})
    group_id = assign_rule_data.get("group_id")
    description = assign_rule_data.get("description", None)

    with session_guard(db.session):
        new_assignment_rule = AssignmentRule(
            org_id=org_id, account=account, name=assign_rule_name, group_id=group_id, filter=filter
        )
        new_assignment_rule.description = description
        db.session.add(new_assignment_rule)
        db.session.flush()

    new_assignment_rule = AssignmentRule.query.filter(
        (AssignmentRule.name == assign_rule_name) & (AssignmentRule.org_id == org_id)
    ).one_or_none()
    return serialize_assignment_rule(new_assignment_rule)
