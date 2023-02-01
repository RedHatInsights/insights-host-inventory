from typing import Optional

import flask
from confluent_kafka import Consumer as KafkaConsumer

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api.filtering.filtering import query_filters
from app import Permission
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
from lib.middleware import rbac
from lib.system_profile_validate import validate_sp_for_branch

logger = get_logger(__name__)

SAP_SYSTEM_QUERY = """
    query hostSystemProfile (
        $hostFilter: [HostFilter]
        $limit: Int
        $offset: Int
    ) {
        hostSystemProfile (
            hostFilter: {
                AND: $hostFilter,
            }
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
        $hostFilter: [HostFilter]
        $filter: SapSidFilter
        $limit: Int
        $offset: Int
    ) {
        hostSystemProfile (
            hostFilter: {
                AND: $hostFilter,
            }
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
        $hostFilter: [HostFilter]
        $limit: Int
        $offset: Int
    ) {
        hostSystemProfile (
            hostFilter: {
                AND: $hostFilter,
            }
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


def _get_query_variables(tags, page, per_page, staleness, registered_with, filter):
    limit, offset = pagination_params(page, per_page)

    all_filters = query_filters(
        tags=tags,
        staleness=staleness,
        registered_with=registered_with,
        filter=filter,
    )

    return {
        "hostFilter": all_filters,
        "limit": limit,
        "offset": offset,
    }


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_system(tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None):
    variables = _get_query_variables(tags, page, per_page, staleness, registered_with, filter)

    response = graphql_query(SAP_SYSTEM_QUERY, variables, log_get_sap_system_failed)
    data = response["hostSystemProfile"]

    check_pagination(variables["offset"], data["sap_system"]["meta"]["total"])

    log_get_sap_system_succeeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_system"]["data"], page, per_page, data["sap_system"]["meta"]["total"])
    )


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_sids(search=None, tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None):
    variables = _get_query_variables(tags, page, per_page, staleness, registered_with, filter)

    # Add search filter (only applies to SAP SIDs endpoint)
    if search:
        variables["filter"] = {"search": {"regex": f".*{custom_escape(search)}.*"}}

    response = graphql_query(SAP_SIDS_QUERY, variables, log_get_sap_sids_failed)
    data = response["hostSystemProfile"]

    check_pagination(variables["offset"], data["sap_sids"]["meta"]["total"])

    log_get_sap_sids_succeeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_sids"]["data"], page, per_page, data["sap_sids"]["meta"]["total"])
    )


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_operating_system(
    tags=None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    staleness: Optional[str] = None,
    registered_with: Optional[str] = None,
    filter=None,
):
    variables = _get_query_variables(tags, page, per_page, staleness, registered_with, filter)

    response = graphql_query(OPERATING_SYSTEM_QUERY, variables, log_get_operating_system_failed)
    data = response["hostSystemProfile"]

    check_pagination(variables["offset"], data["operating_system"]["meta"]["total"])

    log_get_operating_system_succeeded(logger, data)
    return flask_json_response(
        build_collection_response(
            data["operating_system"]["data"], page, per_page, data["operating_system"]["meta"]["total"]
        )
    )


@api_operation
@rbac(Permission.READ)
@metrics.schema_validation_time.time()
def validate_schema(repo_fork="RedHatInsights", repo_branch="master", days=1, max_messages=10000):
    # Use the identity header to make sure the user is someone from our team.
    config = Config(RuntimeEnvironment.SERVICE)
    identity = get_current_identity()
    if not hasattr(identity, "user") or identity.user.get("username") not in config.sp_authorized_users:
        flask.abort(403, "This endpoint is restricted to HBI Admins.")

    consumer = KafkaConsumer(
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.validator_kafka_consumer,
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
