from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import abort
from marshmallow import ValidationError
from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from app.auth import get_current_identity
from app.exceptions import InventoryException
from app.instrumentation import log_patch_group_failed
from app.logging import get_logger
from app.models import Group
from app.models import HostGroupAssoc
from app.models import InputGroupSchema
from app.models import db
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import serialize_group
from lib.host_repository import get_host_list_by_id_list_from_db

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


def validate_patch_group_inputs(group_id: str, body: dict[str, Any], identity: Any) -> tuple[dict[str, Any], Any]:
    """
    Validate inputs for group patching:
    - Group exists
    - Request body is valid
    - Host IDs (if provided) exist

    Args:
        group_id: The ID of the group to patch
        body: The request body containing patch data
        identity: The current user's identity object

    Returns:
        tuple: (validated_patch_group_data, group_to_update)
    """

    # First, get the group and update it
    group_to_update = get_group_by_id_from_db(group_id, identity.org_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        abort(HTTPStatus.NOT_FOUND)

    try:
        validated_patch_group_data = InputGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching group: {group_id} - {body}")
        abort(HTTPStatus.BAD_REQUEST, str(e.messages))

    host_id_list = validated_patch_group_data.get("host_ids")

    # Only validate hosts if host_ids are provided
    if host_id_list is not None:
        # Reuse existing validation logic from lib/group_repository.py
        # Check if the hosts exist in Inventory and have correct org_id
        found_hosts = get_host_list_by_id_list_from_db(host_id_list, identity).all()
        found_host_ids = {str(host.id) for host in found_hosts}

        if found_host_ids != set(host_id_list):
            nonexistent_hosts = set(host_id_list) - found_host_ids
            log_patch_group_failed(logger, group_id)
            abort(HTTPStatus.BAD_REQUEST, f"Host with ID {list(nonexistent_hosts)[0]} not found.")

        # Check if the hosts are already associated with another (ungrouped) group
        if assoc_query := (
            db.session.query(HostGroupAssoc)
            .join(Group)
            .filter(
                HostGroupAssoc.host_id.in_(host_id_list),
                HostGroupAssoc.group_id != group_id,
                Group.ungrouped.is_(False),
            )
            .all()
        ):
            taken_hosts = [str(assoc.host_id) for assoc in assoc_query]
            log_patch_group_failed(logger, group_id)
            raise InventoryException(
                title="Invalid request",
                detail=f"The following subset of hosts are already associated with another group: {taken_hosts}.",
            )

    return validated_patch_group_data, group_to_update
