from sqlalchemy import asc, desc, func
from app.auth import get_current_identity
from app.models import AssignmentRule

# TODO: the following is not needed but for now paste it.
ASSIGNMENT_RULE_ORDER_BY_MAPPING = {
    "name": AssignmentRule.name,
    "host_ids": func.count(HostGroupAssoc.host_id),
}

ASSIGNMENT_RULE_ORDER_HOW_MAPPING = {"asc": asc, "desc": desc, "name": asc, "assignment_rule_ids": desc}


def get_filtered_assignment_rule_list_db(filters, page, per_page, param_order_by, param_order_how, rbac_filter):
    # Apply RBAC group ID filter, if provided
    if rbac_filter and "groups" in rbac_filter:
        filters += (AssignmentRule.id.in_(rbac_filter["groups"]),)

    order_by_str = param_order_by or "name"
    order_by = ASSIGNMENT_RULE_ORDER_BY_MAPPING[order_by_str]
    order_how_func = (
        ASSIGNMENT_RULE_ORDER_HOW_MAPPING[param_order_how.lower()]
        if param_order_how
        else GROUPS_ORDER_HOW_MAPPING[order_by_str]
    )

    # Order the list of groups, then offset and limit based on page and per_page
    group_list = (
        AssignmentRule.query.join(HostGroupAssoc, isouter=True)
        .filter(*filters)
        .group_by(AssignmentRule.id)
        .order_by(order_how_func(order_by))
        .order_by(AssignmentRule.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Get the total number of groups that would be returned using just the filters
    total = db.session.query(func.count(AssignmentRule.id)).filter(*filters).scalar()

    return group_list, total


def get_filtered_group_list_db(group_name, page, per_page, order_by, order_how, rbac_filter):
    filters = (AssignmentRule.org_id == get_current_identity().org_id,)
    if group_name:
        filters += (func.lower(AssignmentRule.name).contains(func.lower(group_name)),)
    return get_group_list_from_db(filters, page, per_page, order_by, order_how, rbac_filter)

