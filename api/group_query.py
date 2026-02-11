from __future__ import annotations

from flask import abort
from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app.auth import get_current_identity
from app.config import MAX_GROUPS_FOR_HOST_COUNT_SORTING
from app.logging import get_logger
from app.models import Group
from app.models import HostGroupAssoc
from app.models import db
from app.serialization import serialize_rbac_workspace_with_host_count
from lib.group_repository import serialize_group
from lib.host_repository import get_group_ids_ordered_by_host_count
from lib.host_repository import get_host_counts_batch
from lib.middleware import get_rbac_workspaces
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


def _get_groups_ordered_by_host_count_no_filters(
    org_id: str,
    page: int,
    per_page: int,
    order_how: str | None,
) -> dict:
    """
    Scenario 1: No filters - Most efficient approach.
    Let the database do ordering and pagination, then fetch only the workspaces we need.

    Args:
        org_id: Organization ID
        page: Page number (1-based)
        per_page: Items per page
        order_how: Sort direction ('ASC' or 'DESC')

    Returns:
        Dictionary with paginated response structure
    """
    # Step 1: Get group_ids ordered by host_count from DB (paginated)
    group_ids_page, total = get_group_ids_ordered_by_host_count(org_id, per_page, page, order_how)

    if not group_ids_page:
        # No groups found
        return build_paginated_group_list_response(total, page, per_page, [])

    # Step 2: Fetch workspace details for only this page of groups
    workspaces = get_rbac_workspaces_by_ids(group_ids_page)

    # Step 3: Get host counts for these groups in one batch query
    host_counts = get_host_counts_batch(org_id, group_ids_page)

    # Step 4: Serialize workspaces with pre-fetched host counts
    serialized_groups = [
        serialize_rbac_workspace_with_host_count(ws, org_id, host_counts.get(ws["id"], 0)) for ws in workspaces
    ]

    # Step 5: Maintain the DB ordering (workspaces may be in different order)
    # Create a map for O(1) lookup
    group_map = {g["id"]: g for g in serialized_groups}
    ordered_groups = [group_map[gid] for gid in group_ids_page if gid in group_map]

    return {
        "total": total,
        "count": len(ordered_groups),
        "page": page,
        "per_page": per_page,
        "results": ordered_groups,
    }


def _get_groups_ordered_by_host_count_with_filters(
    org_id: str,
    name: str | None,
    group_type: str | None,
    page: int,
    per_page: int,
    order_how: str | None,
) -> dict:
    """
    Scenario 2: With filters - RBAC v2 must filter, then DB orders by host_count.
    Fetch all filtered workspaces, add host counts, and sort client-side.

    Args:
        org_id: Organization ID
        name: Filter by workspace name (partial match)
        group_type: Filter by workspace type (standard, ungrouped-hosts)
        page: Page number (1-based)
        per_page: Items per page
        order_how: Sort direction ('ASC' or 'DESC')

    Returns:
        Dictionary with paginated response structure

    Raises:
        HTTPException: HTTP 400 if filtering results in too many groups to sort
    """
    # Step 1: Fetch all filtered workspaces from RBAC v2
    # Limit is configurable via MAX_GROUPS_FOR_HOST_COUNT_SORTING env variable
    result = get_rbac_workspaces(name, 1, MAX_GROUPS_FOR_HOST_COUNT_SORTING, group_type, None, None)
    if result is None:
        return build_paginated_group_list_response(0, page, per_page, [])
    group_list, total = result

    # Validate that we can sort all groups
    if total > MAX_GROUPS_FOR_HOST_COUNT_SORTING:
        abort(
            400,
            f"Cannot sort by host_count: organization has {total} groups, which exceeds "
            f"the maximum of {MAX_GROUPS_FOR_HOST_COUNT_SORTING} groups that can be sorted. "
            f"Please use filters (name, group_type) to narrow your results, or use a different "
            f"ordering field (name, updated, created, type).",
        )

    if not group_list:
        # No groups found
        return build_paginated_group_list_response(total, page, per_page, [])

    # Step 2: Extract group_ids
    group_ids = [ws["id"] for ws in group_list]

    # Step 3: Fetch ALL host counts in ONE batch query (not N queries!)
    host_counts = get_host_counts_batch(org_id, group_ids)

    # Step 4: Attach host_counts to workspaces (no DB queries!)
    serialized_groups = [
        serialize_rbac_workspace_with_host_count(ws, org_id, host_counts.get(ws["id"], 0)) for ws in group_list
    ]

    # Step 5: Sort by host_count with secondary sort by name for stable ordering
    serialized_groups.sort(key=lambda g: g.get("name", ""))  # Secondary: name (ASC)
    reverse = order_how == "DESC" if order_how else True  # Default DESC for host_count
    serialized_groups.sort(key=lambda g: g.get("host_count", 0), reverse=reverse)

    # Step 6: Apply pagination to sorted results
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_groups = serialized_groups[start_idx:end_idx]

    return {
        "total": total,
        "count": len(paginated_groups),
        "page": page,
        "per_page": per_page,
        "results": paginated_groups,
    }


def get_workspaces_from_rbac_v2(
    org_id: str,
    name: str | None,
    group_type: str | None,
    page: int,
    per_page: int,
    order_how: str | None,
) -> dict:
    """
    Handle GET /groups with RBAC v2 when ordering by host_count.

    RBAC v2 doesn't have host count data in workspaces, so we use a hybrid approach:
    - Scenario 1 (no filters): Database orders by host_count, then fetch workspaces for that page
    - Scenario 2 (with filters): Fetch all filtered workspaces from RBAC v2, add counts, sort client-side

    Args:
        org_id: Organization ID
        name: Filter by workspace name (partial match)
        group_type: Filter by workspace type (standard, ungrouped-hosts)
        page: Page number (1-based)
        per_page: Items per page
        order_how: Sort direction ('ASC' or 'DESC')

    Returns:
        Dictionary with paginated response structure (total, count, page, per_page, results)

    Raises:
        HTTPException: HTTP 400 if filtering results in too many groups to sort
    """
    # Route to appropriate scenario
    if not name and not group_type:
        return _get_groups_ordered_by_host_count_no_filters(org_id, page, per_page, order_how)
    else:
        return _get_groups_ordered_by_host_count_with_filters(org_id, name, group_type, page, per_page, order_how)
