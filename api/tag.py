import flask

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api import pagination_params
from api.host_query_db import get_tag_list as get_tag_list_db
from app import RbacPermission
from app import RbacResourceType
from app.instrumentation import log_get_tags_failed
from app.instrumentation import log_get_tags_succeeded
from app.logging import get_logger
from lib.middleware import rbac

logger = get_logger(__name__)


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
    escaped_search = None
    if search:
        # Escaped so that the string literals are not interpreted as regex
        escaped_search = f".*{custom_escape(search)}.*"

    try:
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
        log_get_tags_succeeded(logger, results)
        return flask_json_response(build_collection_response(results, page, per_page, total))

    except ValueError as e:
        log_get_tags_failed(logger)
        flask.abort(400, str(e))
