from __future__ import annotations

from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app.auth import get_current_identity
from app.logging import get_logger
from app.models import Group
from app.models import HostGroupAssoc
from app.models import db
from app.serialization import serialize_rbac_workspace_with_host_count
from lib.group_repository import serialize_group
from lib.host_repository import get_host_counts_batch
from lib.middleware import get_rbac_workspaces_by_ids

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
    "created": Group.created_on,  # ADDED for RBAC v2
    "type": Group.ungrouped,  # ADDED for RBAC v2
}

GROUPS_ORDER_HOW_MAPPING = {
    "asc": asc,
    "desc": desc,
    "name": asc,
    "host_count": desc,
    "updated": desc,
    "created": desc,  # ADDED for RBAC v2
    "type": asc,  # ADDED for RBAC v2
}
GROUP_TYPE_MAPPING = {
    "standard": Group.ungrouped.is_(False),
    "ungrouped-hosts": Group.ungrouped.is_(True),
}

__all__ = (
    "build_paginated_group_list_response",
    "build_group_response",
    "get_group_list_by_id_list_db",
    "get_group_list_by_id_list_rbac_v2",
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


def get_group_list_by_id_list_rbac_v2(
    group_id_list,
    page,
    per_page,
    order_by,
    order_how,
):
    """
    Fetch group list from RBAC v2 API by ID list with ordering and pagination.

    This is the RBAC v2 equivalent of get_group_list_by_id_list_db().
    Fetches workspaces from RBAC v2 API, enriches with host counts from database,
    applies ordering and pagination, and returns serialized results.

    Args:
        group_id_list: List of group UUIDs to fetch
        page: Page number (1-indexed)
        per_page: Number of results per page
        order_by: Field to order by ("name", "host_count", "updated")
        order_how: Sort direction ("asc" or "desc")

    Note:
        Unlike get_group_list_by_id_list_db(), this function does not take an rbac_filter
        parameter. RBAC filtering is already enforced by rbac_group_id_check() before this
        function is called (see api/group.py line 300), which validates that all requested
        group_id_list entries are in the allowed rbac_filter["groups"] set. Additional
        filtering here would be redundant.

    Returns:
        tuple: (group_list, total) where:
            - group_list: List of serialized group dicts (already paginated)
            - total: Total number of groups (before pagination)
    """
    identity = get_current_identity()

    # Fetch workspaces from RBAC v2 API
    workspaces = get_rbac_workspaces_by_ids(group_id_list)

    # Fetch all host counts in ONE batch query (eliminates N+1 problem)
    host_counts = get_host_counts_batch(identity.org_id, [ws["id"] for ws in workspaces])

    # Serialize with pre-fetched host counts
    group_list = [
        serialize_rbac_workspace_with_host_count(workspace, host_counts.get(workspace["id"], 0), identity)
        for workspace in workspaces
    ]

    total = len(group_list)

    # Apply ordering (same logic as RBAC v1 database path)
    order_by_field = order_by or "name"

    # Determine sort direction
    # Explicit order_how parameter takes precedence, otherwise use default from GROUPS_ORDER_HOW_MAPPING
    # name: asc (default), host_count: desc, updated: desc
    reverse = order_how.lower() == "desc" if order_how else GROUPS_ORDER_HOW_MAPPING.get(order_by_field) == desc

    # For stable ordering matching database's ORDER BY primary_field, Group.id:
    # Sort by id first (tiebreaker), then by primary field.
    # Python's stable sort preserves id ordering for items with equal primary keys.
    group_list.sort(key=lambda g: g["id"])
    if order_by_field == "name":
        group_list.sort(key=lambda g: g["name"].lower() if g.get("name") else "", reverse=reverse)
    elif order_by_field == "host_count":
        group_list.sort(key=lambda g: g.get("host_count", 0), reverse=reverse)
    elif order_by_field == "updated":
        group_list.sort(key=lambda g: g.get("updated", ""), reverse=reverse)

    # Apply pagination
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    paginated_group_list = group_list[start_index:end_index]

    return paginated_group_list, total


def does_group_with_name_exist(group_name: str, org_id: str):
    """
    Check if a group with the given name exists in the database.

    Parameters:
    - group_name (str): The name of the group to check.
    - org_id (str): The ID of the organization to filter by.

    Returns:
    bool: True if a group with the given name exists, False otherwise.
    """
    return db.session.query(
        db.exists().where(func.lower(Group.name) == func.lower(group_name), Group.org_id == org_id)
    ).scalar()


def get_filtered_group_list_db(group_name, page, per_page, order_by, order_how, rbac_filter, group_type=None):
    filters = (Group.org_id == get_current_identity().org_id,)
    if (type_filter := GROUP_TYPE_MAPPING.get(group_type)) is not None:
        filters += (type_filter,)
    if group_name:
        filters += (func.lower(Group.name).contains(func.lower(group_name)),)
    return get_group_list_from_db(filters, page, per_page, order_by, order_how, rbac_filter)


def build_paginated_group_list_response(total, page, per_page, group_list):
    # group resource provided by rbac_v2 does not have org_id
    org_id = get_current_identity().org_id
    json_group_list = [serialize_group(group, org_id) for group in group_list]
    return {
        "total": total,
        "count": len(json_group_list),
        "page": page,
        "per_page": per_page,
        "results": json_group_list,
    }


def build_group_response(group):
    # group resource provided by RBAC V2 API does not have org_id
    org_id = get_current_identity().org_id
    return serialize_group(group, org_id)
