import flask

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api.filtering.filtering import query_filters
from api.host_query_db import get_tag_list as get_tag_list_db
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.exceptions import ValidationException
from app.instrumentation import log_get_tags_failed
from app.instrumentation import log_get_tags_succeeded
from app.logging import get_logger
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from lib.feature_flags import FLAG_INVENTORY_DISABLE_XJOIN
from lib.feature_flags import get_flag_value
from lib.middleware import rbac

logger = get_logger(__name__)

TAGS_QUERY = """
    query hostTags (
        $hostFilter: [HostFilter!],
        $filter: TagAggregationFilter,
        $order_by: HOST_TAGS_ORDER_BY,
        $order_how: ORDER_DIR,
        $limit: Int,
        $offset: Int
    ) {
        hostTags (
            hostFilter: {
                AND: $hostFilter,
            },
            filter: $filter,
            order_by: $order_by,
            order_how: $order_how,
            limit: $limit,
            offset: $offset
        ) {
            meta {
                total
            }
            data {
                tag {
                    namespace, key, value
                },
                count
            }
        }
    }
"""


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_tags(
    search=None,
    tags=None,
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    provider_id=None,
    provider_type=None,
    updated_start=None,
    updated_end=None,
    group_name=None,
    order_by=None,
    order_how=None,
    page=None,
    per_page=None,
    staleness=None,
    registered_with=None,
    filter=None,
    rbac_filter=None,
):
    limit, offset = pagination_params(page, per_page)
    current_identity = get_current_identity()
    is_bootc = filter.get("system_profile", {}).get("bootc_status")
    escaped_search = None
    if search:
        # Escaped so that the string literals are not interpreted as regex
        escaped_search = f".*{custom_escape(search)}.*"

    try:
        if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}) or is_bootc:
            results, total = get_tag_list_db(
                limit=limit,
                offset=offset,
                search=escaped_search,
                tags=tags,
                display_name=display_name,
                fqdn=fqdn,
                hostname_or_id=hostname_or_id,
                insights_id=insights_id,
                provider_id=provider_id,
                provider_type=provider_type,
                updated_start=updated_start,
                updated_end=updated_end,
                group_name=group_name,
                order_by=order_by,
                order_how=order_how,
                staleness=staleness,
                registered_with=registered_with,
                filter=filter,
                rbac_filter=rbac_filter,
            )
            return flask_json_response(build_collection_response(results, page, per_page, total))

        variables = {
            "order_by": order_by,
            "order_how": order_how,
            "limit": limit,
            "offset": offset,
            "hostFilter": {},
        }

        hostfilter_and_variables = query_filters(
            fqdn,
            display_name,
            hostname_or_id,
            insights_id,
            provider_id,
            provider_type,
            updated_start,
            updated_end,
            group_name,
            None,
            tags,
            staleness,
            registered_with,
            filter,
            rbac_filter,
        )
    # except ValueError as e:
    except (ValidationException, ValueError) as ve:
        log_get_tags_failed(logger)
        flask.abort(400, str(ve))

    if escaped_search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": escaped_search}
        }

    if hostfilter_and_variables != ():
        variables["hostFilter"] = hostfilter_and_variables

    response = graphql_query(TAGS_QUERY, variables, log_get_tags_failed)
    data = response["hostTags"]

    check_pagination(offset, data["meta"]["total"])

    log_get_tags_succeeded(logger, data)
    return flask_json_response(build_collection_response(data["data"], page, per_page, data["meta"]["total"]))
