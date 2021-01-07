import json
import re
from datetime import datetime
from datetime import timedelta

import flask
from kafka import KafkaConsumer
from kafka.common import TopicPartition
from requests import get
from yaml import safe_load

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from api.host import get_bulk_query_source
from api.host_query_xjoin import build_sap_sids_filter
from api.host_query_xjoin import build_sap_system_filters
from api.host_query_xjoin import build_tag_query_dict_tuple
from app import Permission
from app.config import BulkQuerySource
from app.config import Config
from app.environment import RuntimeEnvironment
from app.instrumentation import log_get_sap_sids_failed
from app.instrumentation import log_get_sap_sids_succeeded
from app.instrumentation import log_get_sap_system_failed
from app.instrumentation import log_get_sap_system_succeeded
from app.logging import get_logger
from app.queue.queue import OperationSchema
from app.serialization import deserialize_host_mq
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from lib.middleware import rbac

logger = get_logger(__name__)


SAP_SYSTEM_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_system {
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
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_sids (
                filter: $filter
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


def xjoin_enabled():
    return get_bulk_query_source() == BulkQuerySource.xjoin


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_system(tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        }
    }
    hostfilter_and_variables = ()

    if tags:
        hostfilter_and_variables = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    if filter:
        if filter.get("system_profile"):
            if filter["system_profile"].get("sap_system"):
                hostfilter_and_variables += build_sap_system_filters(filter["system_profile"].get("sap_system"))
            if filter["system_profile"].get("sap_sids"):
                hostfilter_and_variables += build_sap_sids_filter(filter["system_profile"]["sap_sids"])

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
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_sids(search=None, tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        }
    }

    hostfilter_and_variables = ()

    if tags:
        hostfilter_and_variables = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    if search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": f".*{re.escape(search)}.*"}
        }

    if filter:
        if filter.get("system_profile"):
            if filter["system_profile"].get("sap_system"):
                hostfilter_and_variables += build_sap_system_filters(filter["system_profile"].get("sap_system"))
            if filter["system_profile"].get("sap_sids"):
                hostfilter_and_variables += build_sap_sids_filter(filter["system_profile"]["sap_sids"])

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(SAP_SIDS_QUERY, variables, log_get_sap_sids_failed)

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_sids"]["meta"]["total"])

    log_get_sap_sids_succeeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_sids"]["data"], page, per_page, data["sap_sids"]["meta"]["total"])
    )


class TestResult:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0


def validate_host_list(host_list, repo_branch):
    system_profile_spec = safe_load(
        get(
            (
                "https://raw.githubusercontent.com/RedHatInsights/inventory-schemas/"
                f"{repo_branch}/schemas/system_profile/v1.yaml"
            ),
            verify=False,
        ).content.decode("utf-8")
    )

    print(f"Validating host against {repo_branch} schema...")
    test_results = {}

    for host in host_list:
        if host["reporter"] not in test_results.keys():
            test_results[host["reporter"]] = TestResult()
        try:
            deserialize_host_mq(host, system_profile_spec)
            test_results[host["reporter"]].pass_count += 1
        except Exception as e:
            test_results[host["reporter"]].fail_count += 1
            logger.exception(e)

    return test_results


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def validate_schema(repo_branch="master", days=14):
    config = Config(RuntimeEnvironment.SERVICE)

    consumer = KafkaConsumer(
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.kafka_consumer,
    )

    tp = TopicPartition(config.host_ingress_topic, 0)
    consumer.assign([tp])

    seek_date = datetime.now() + timedelta(days=(-1 * days))
    seek_position = max(consumer.offsets_for_times({tp: seek_date.timestamp() * 1000})[tp].offset, 0)

    consumer.seek_to_beginning(tp)
    consumer.seek(tp, seek_position)
    msgs = consumer.poll(timeout_ms=10000, max_records=10000)
    hosts_parsed = 0
    parsed_hosts = []

    for topic_partition, messages in msgs.items():
        for message in messages:
            parsed_message = json.loads(message.value)
            parsed_operation = OperationSchema(strict=True).load(parsed_message).data
            parsed_hosts.append(parsed_operation["data"])
            hosts_parsed += 1

    logger.info(f"Parsed {hosts_parsed} hosts from message queue.")

    response_data = {}
    for branch in ["master", repo_branch]:
        response_data[branch] = validate_host_list(parsed_hosts, repo_branch)

    return flask_json_response(response_data)
