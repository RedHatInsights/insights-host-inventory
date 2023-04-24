from flask import abort
from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import func

from api.filtering.filtering import query_filters
from app import db
from app.auth import get_current_identity
from app.instrumentation import log_get_group_list_failed
from app.logging import get_logger
from app.models import Group
from app.serialization import deserialize_group_xjoin
from app.serialization import serialize_group
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import groups_params_to_order
from app.xjoin import pagination_params


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
                id, name, account, org_id, created_on, modified_on
            },
            count
        }
    }
}"""

GROUPS_ORDER_BY_MAPPING = {
    None: Group.name,
    "name": Group.name,
    "host_ids": Group.hosts,
}

GROUPS_ORDER_HOW_MAPPING = {Group.name: asc, Group.hosts: desc}

__all__ = (
    "build_paginated_group_list_response",
    "build_group_response",
    "get_group_list_by_id_list",
    "get_group_list_using_filters",
    "get_filtered_group_list",
)


def get_group_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how):
    limit, offset = pagination_params(page, per_page)
    xjoin_order_by, xjoin_order_how = groups_params_to_order(param_order_by, param_order_how)

    variables = {
        "limit": limit,
        "offset": offset,
        "order_by": xjoin_order_by,
        "order_how": xjoin_order_how,
        "hostFilter": all_filters,
    }
    response = graphql_query(QUERY, variables, log_get_group_list_failed)
    if response is None or "hostGroups" not in response:
        # Log an error implicating xjoin, then abort with status 503
        logger.error("xjoin-search responded with invalid format")
        abort(503)

    response = response["hostGroups"]

    total = response["meta"]["total"]
    check_pagination(offset, total)

    return map(deserialize_group_xjoin, response["data"]), total


def get_group_list_by_id_list(group_id_list, page, per_page, order_by, order_how):
    all_filters = query_filters(group_ids=group_id_list)
    return get_group_list_using_filters(all_filters, page, per_page, order_by, order_how)


def get_filtered_group_list(group_name, page, per_page, order_by, order_how):
    all_filters = query_filters(group_name=group_name)
    return get_group_list_using_filters(all_filters, page, per_page, order_by, order_how)


def get_group_list_from_db(filters, page, per_page, param_order_by, param_order_how):
    order_by = GROUPS_ORDER_BY_MAPPING[param_order_by]
    order_how_func = param_order_how or GROUPS_ORDER_HOW_MAPPING[order_by]

    # Order the list of groups, then offset and limit based on page and per_page
    group_list = (
        db.session.query(Group)
        .filter(*filters)
        .order_by(order_how_func(order_by))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Get the total number of groups that would be returned using just the filters
    total = db.session.query(func.count(Group.id)).filter(*filters).scalar()

    if len(group_list) == 0:
        abort(404)

    return group_list, total


def get_group_list_by_id_list_db(group_id_list, page, per_page, order_by, order_how):
    filters = (
        Group.org_id == get_current_identity().org_id,
        Group.id.in_(group_id_list),
    )
    return get_group_list_from_db(filters, page, per_page, order_by, order_how)


def get_filtered_group_list_db(group_name, page, per_page, order_by, order_how):
    filters = (Group.org_id == get_current_identity().org_id,)
    if group_name:
        filters += (Group.name == group_name,)
    return get_group_list_from_db(filters, page, per_page, order_by, order_how)


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
