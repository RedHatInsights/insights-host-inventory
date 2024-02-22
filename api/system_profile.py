from typing import Optional

import flask
from confluent_kafka import Consumer as KafkaConsumer

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api.filtering.filtering import query_filters
from api.host_query_db import get_os_info as get_os_info_db
from api.host_query_db import get_sap_sids_info as get_sap_sids_info_db
from api.host_query_db import get_sap_system_info as get_sap_system_info_db
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.config import Config
from app.environment import RuntimeEnvironment
from app.instrumentation import log_get_operating_system_failed
from app.instrumentation import log_get_operating_system_succeeded
from app.instrumentation import log_get_sap_sids_failed
from app.instrumentation import log_get_sap_sids_succeeded
from app.instrumentation import log_get_sap_system_failed
from app.instrumentation import log_get_sap_system_succeeded
from app.logging import get_logger
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from lib.feature_flags import FLAG_INVENTORY_DISABLE_XJOIN
from lib.feature_flags import get_flag_value
from lib.middleware import rbac
from lib.system_profile_validate import validate_sp_for_branch

logger = get_logger(__name__)

SAP_SYSTEM_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
        $limit: Int
        $offset: Int
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_system (
                limit: $limit
                offset: $offset
            ) {
                meta{
                    total
                    count
                }
                data {
                    value
                    count
                }
            }
        }
    }
"""

SAP_SIDS_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
        $filter: SapSidFilter
        $limit: Int
        $offset: Int
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_sids (
                filter: $filter
                limit: $limit
                offset: $offset
            ) {
                meta {
                    total
                    count
                }
                data {
                    value
                    count
                }
            }
        }
    }
"""

OPERATING_SYSTEM_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
        $limit: Int
        $offset: Int
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            operating_system (
                limit: $limit
                offset: $offset
            ) {
                meta {
                    total
                    count
                }
                data {
                    value {
                        name
                        major
                        minor
                    }
                    count
                }
            }
        }
    }
"""


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_sap_system(
    tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None, rbac_filter=None
):
    limit, offset = pagination_params(page, per_page)
    current_identity = get_current_identity()
    if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
        results, total = get_sap_system_info_db(
            limit,
            offset,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            filter=filter,
            rbac_filter=rbac_filter,
        )
        return flask_json_response(build_collection_response(results, page, per_page, total))

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        },
        "limit": limit,
        "offset": offset,
    }

    hostfilter_and_variables = query_filters(tags=tags, registered_with=registered_with, filter=filter)

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(SAP_SYSTEM_QUERY, variables, log_get_sap_system_failed)

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_system"]["meta"]["total"])

    log_get_sap_system_succeeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_system"]["data"], page, per_page, data["sap_system"]["meta"]["total"])
    )


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
    current_identity = get_current_identity()
    escaped_search = None
    if search:
        # Escaped so that the string literals are not interpreted as regex
        escaped_search = f".*{custom_escape(search)}.*"
    if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
        results, total = get_sap_sids_info_db(
            limit,
            offset,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            filter=filter,
            rbac_filter=rbac_filter,
            search=escaped_search,
        )
        return flask_json_response(build_collection_response(results, page, per_page, total))

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        },
        "limit": limit,
        "offset": offset,
    }

    if escaped_search:
        variables["filter"] = {"search": {"regex": escaped_search}}

    hostfilter_and_variables = query_filters(
        tags=tags, registered_with=registered_with, filter=filter, rbac_filter=rbac_filter
    )

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(SAP_SIDS_QUERY, variables, log_get_sap_sids_failed)

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_sids"]["meta"]["total"])

    log_get_sap_sids_succeeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_sids"]["data"], page, per_page, data["sap_sids"]["meta"]["total"])
    )


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_operating_system(
    tags=None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    staleness: Optional[str] = None,
    registered_with: Optional[str] = None,
    filter=None,
    rbac_filter=None,
):
    limit, offset = pagination_params(page, per_page)
    current_identity = get_current_identity()
    if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
        results, total = get_os_info_db(
            limit,
            offset,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            filter=filter,
            rbac_filter=rbac_filter,
        )
        return flask_json_response(build_collection_response(results, page, per_page, total))
    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        },
        "limit": limit,
        "offset": offset,
    }

    hostfilter_and_variables = query_filters(
        tags=tags, registered_with=registered_with, filter=filter, rbac_filter=rbac_filter
    )

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(OPERATING_SYSTEM_QUERY, variables, log_get_operating_system_failed)

    data = response["hostSystemProfile"]

    check_pagination(offset, data["operating_system"]["meta"]["total"])

    log_get_operating_system_succeeded(logger, data)

    return flask_json_response(
        build_collection_response(
            data["operating_system"]["data"], page, per_page, data["operating_system"]["meta"]["total"]
        )
    )


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
