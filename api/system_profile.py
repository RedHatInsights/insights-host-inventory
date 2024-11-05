from typing import Optional

import flask
from confluent_kafka import Consumer as KafkaConsumer

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api import pagination_params
from api.host_query_db import get_os_info
from api.host_query_db import get_sap_sids_info
from api.host_query_db import get_sap_system_info
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.config import Config
from app.environment import RuntimeEnvironment
from app.instrumentation import log_get_operating_system_succeeded
from app.instrumentation import log_get_sap_sids_succeeded
from app.instrumentation import log_get_sap_system_succeeded
from app.logging import get_logger
from lib.middleware import rbac
from lib.system_profile_validate import validate_sp_for_branch

logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_sap_system(
    tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None, rbac_filter=None
):
    results, total = get_sap_system_info(
        page,
        per_page,
        staleness=staleness,
        tags=tags,
        registered_with=registered_with,
        filter=filter,
        rbac_filter=rbac_filter,
    )
    log_get_sap_system_succeeded(logger, results)
    return flask_json_response(build_collection_response(results, page, per_page, total))


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_sap_sids(
    search=None,
    tags=None,
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

    results, total = get_sap_sids_info(
        limit,
        offset,
        staleness=staleness,
        tags=tags,
        registered_with=registered_with,
        filter=filter,
        rbac_filter=rbac_filter,
        search=escaped_search,
    )
    log_get_sap_sids_succeeded(logger, results)
    return flask_json_response(build_collection_response(results, page, per_page, total))


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_operating_system(
    tags=None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    staleness: Optional[list[str]] = None,
    registered_with: Optional[list[str]] = None,
    filter=None,
    rbac_filter=None,
):
    limit, offset = pagination_params(page, per_page)
    results, total = get_os_info(
        limit,
        offset,
        staleness=staleness,
        tags=tags,
        registered_with=registered_with,
        filter=filter,
        rbac_filter=rbac_filter,
    )
    log_get_operating_system_succeeded(logger, results)
    return flask_json_response(build_collection_response(results, page, per_page, total))


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.schema_validation_time.time()
def validate_schema(repo_fork="RedHatInsights", repo_branch="master", days=1, max_messages=10000, rbac_filter=None):
    # Use the identity header to make sure the user is someone from our team.
    config = Config(RuntimeEnvironment.SERVICE)
    identity = get_current_identity()
    if not hasattr(identity, "user") or identity.user.get("username") not in config.sp_authorized_users:
        flask.abort(403, "This endpoint is restricted to HBI Admins.")

    consumer = KafkaConsumer(
        {
            "bootstrap.servers": config.bootstrap_servers,
            **config.validator_kafka_consumer,
        }
    )

    try:
        response = validate_sp_for_branch(
            consumer,
            {config.host_ingress_topic, config.additional_validation_topic},
            repo_fork,
            repo_branch,
            days,
            max_messages,
        )
        consumer.close()
        return flask_json_response(response)
    except (ValueError, AttributeError) as e:
        consumer.close()
        flask.abort(400, str(e))
