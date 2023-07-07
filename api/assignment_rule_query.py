from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app import db
from app.auth import get_current_identity
from app.models import Group
from app.models import HostGroupAssoc
from app.serialization import serialize_assignment_rule
from app.serialization import serialize_group


# TODO: the following is not needed but for now paste it.
ASSIGNMENT_RULE_ORDER_BY_MAPPING = {
    "name": Group.name,
    "host_ids": func.count(HostGroupAssoc.host_id),
}

ASSIGNMENT_RULE_ORDER_HOW_MAPPING = {"asc": asc, "desc": desc, "name": asc, "host_ids": desc}


def get_assignment_rules_list_db(filters, page, per_page, param_order_by, param_order_how, rbac_filter):
    # Apply RBAC group ID filter, if provided
    if rbac_filter and "groups" in rbac_filter:
        filters += (Group.id.in_(rbac_filter["groups"]),)

    order_by_str = param_order_by or "name"
    order_by = ASSIGNMENT_RULE_ORDER_BY_MAPPING[order_by_str]
    order_how_func = (
        ASSIGNMENT_RULE_ORDER_HOW_MAPPING[param_order_how.lower()]
        if param_order_how
        else ASSIGNMENT_RULE_ORDER_HOW_MAPPING[order_by_str]
    )

    # Order the list of groups, then offset and limit based on page and per_page
    assingnment_rules_list = (
        Group.query.join(HostGroupAssoc, isouter=True)
        .filter(*filters)
        .group_by(Group.id)
        .order_by(order_how_func(order_by))
        .order_by(Group.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Get the total number of groups that would be returned using just the filters
    total = db.session.query(func.count(Group.id)).filter(*filters).scalar()

    return assingnment_rules_list, total


def get_filtered_assignment_rule_list_db(group_name, page, per_page, order_by, order_how, rbac_filter):
    filters = (Group.org_id == get_current_identity().org_id,)
    if group_name:
        filters += (func.lower(Group.name).contains(func.lower(group_name)),)
    return get_assignment_rules_list_db(filters, page, per_page, order_by, order_how, rbac_filter)


def build_paginated_group_list_response(total, page, per_page, group_list):
    json_group_list = [serialize_assignment_rule(group) for group in group_list]
    return {
        "total": total,
        "count": len(json_group_list),
        "page": page,
        "per_page": per_page,
        "results": json_group_list,
    }


def build_group_response(group):
    return serialize_group(group)
