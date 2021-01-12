import json
from datetime import datetime
from datetime import timedelta

from kafka import KafkaConsumer
from kafka.common import TopicPartition
from requests import get
from yaml import safe_load

from app.logging import get_logger
from app.queue.queue import OperationSchema
from app.serialization import deserialize_host_mq

__all__ = ("validate_sp_for_branch",)

logger = get_logger(__name__)


class TestResult:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0


def _validate_host_list(host_list, repo_branch):
    system_profile_spec = safe_load(
        get(
            "https://raw.githubusercontent.com/RedHatInsights/inventory-schemas/"
            f"{repo_branch}/schemas/system_profile/v1.yaml"
        ).content.decode("utf-8")
    )

    logger.info(f"Validating host against {repo_branch} schema...")
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


def validate_sp_for_branch(config, repo_branch="master", days=14):
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
    consumer.close()

    hosts_parsed = 0
    parsed_hosts = []

    for topic_partition, messages in msgs.items():
        for message in messages:
            parsed_message = json.loads(message.value)
            parsed_operation = OperationSchema(strict=True).load(parsed_message).data
            parsed_hosts.append(parsed_operation["data"])
            hosts_parsed += 1

    logger.info(f"Parsed {hosts_parsed} hosts from message queue.")

    validation_results = {}
    for branch in [repo_branch, "master"]:
        validation_results[branch] = _validate_host_list(parsed_hosts, branch)

    return validation_results
