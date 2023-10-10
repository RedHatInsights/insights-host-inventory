from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app import db
from app.auth import get_current_identity
from app.logging import get_logger
from app.models import Group
from app.models import HostGroupAssoc
from app.serialization import serialize_group


logger = get_logger(__name__)

QUERY = """query Query (
    $hostFilter: [HostFilter!],
    $order_by: HOST_GROUPS_ORDER_BY,
    $order_how: ORDER_DIR,
    $limit: Int,
    $offset: Int
) {
    hostGroups (
        hostFilter: {
            AND: $hostFilter,
        }
        order_by: $order_by,
        order_how: $order_how,
        limit: $limit,
        offset: $offset
    ) {
        meta {
            count,
            total
        }
        data {
            group {
                id, name, account, org_id, created, updated
            },
            count
        }
    }
}"""

GROUPS_ORDER_BY_MAPPING = {
    "name": Group.name,
    "host_count": func.count(HostGroupAssoc.host_id),
    "updated": Group.modified_on,
}

GROUPS_ORDER_HOW_MAPPING = {"asc": asc, "desc": desc, "name": asc, "host_count": desc, "updated": desc}

__all__ = (
    "build_paginated_group_list_response",
    "build_group_response",
    "get_group_list_by_id_list_db",
    "get_filtered_group_list_db",
    "get_group_list_from_db",
)


def get_group_list_from_db(filters, page, per_page, param_order_by, param_order_how, rbac_filter):
    # Apply RBAC group ID filter, if provided
    if rbac_filter and "groups" in rbac_filter:
        filters += (Group.id.in_(rbac_filter["groups"]),)

    order_by_str = param_order_by or "name"
    order_by = GROUPS_ORDER_BY_MAPPING[order_by_str]
    order_how_func = (
        GROUPS_ORDER_HOW_MAPPING[param_order_how.lower()]
        if param_order_how
        else GROUPS_ORDER_HOW_MAPPING[order_by_str]
    )

    # Order the list of groups, then offset and limit based on page and per_page
    group_list = (
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

    return group_list, total


def get_total_group_count_db():
    return Group.query.filter(Group.org_id == get_current_identity().org_id).count()


def get_group_list_by_id_list_db(group_id_list, page, per_page, order_by, order_how, rbac_filter):
    filters = (
        Group.org_id == get_current_identity().org_id,
        Group.id.in_(group_id_list),
    )
    return get_group_list_from_db(filters, page, per_page, order_by, order_how, rbac_filter)


def get_filtered_group_list_db(group_name, page, per_page, order_by, order_how, rbac_filter):
    filters = (Group.org_id == get_current_identity().org_id,)
    if group_name:
        filters += (func.lower(Group.name).contains(func.lower(group_name)),)
    return get_group_list_from_db(filters, page, per_page, order_by, order_how, rbac_filter)


def build_paginated_group_list_response(total, page, per_page, group_list):
    json_group_list = [serialize_group(group) for group in group_list]
    return {
        "total": total,
        "count": len(json_group_list),
        "page": page,
        "per_page": per_page,
        "results": json_group_list,
    }


def build_group_response(group):
    return serialize_group(group)
