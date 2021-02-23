import json
from datetime import datetime
from datetime import timedelta

from kafka.common import TopicPartition
from marshmallow import ValidationError
from requests import get
from yaml import safe_load

from app.logging import get_logger
from app.queue.queue import OperationSchema
from app.serialization import deserialize_host

__all__ = ("validate_sp_for_branch",)

logger = get_logger(__name__)


class TestResult:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0


def get_schema_from_url(url):
    response = get(url)
    if response.status_code != 200:
        raise ValueError(f"Schema not found at URL: {url}")
    return safe_load(get(url).content.decode("utf-8"))


def validate_host_list_against_spec(host_list, sp_spec):
    test_results = {}
    for host in host_list:
        if not host.get("reporter"):
            host["reporter"] = "unknown_reporter"
        if host["reporter"] not in test_results.keys():
            test_results[host["reporter"]] = TestResult()
        try:
            deserialize_host(host, system_profile_spec=sp_spec)
            test_results[host["reporter"]].pass_count += 1
        except Exception as e:
            test_results[host["reporter"]].fail_count += 1
            logger.exception(e)

    return test_results


def _validate_host_list(host_list, repo_config):
    system_profile_spec = get_schema_from_url(
        f"https://raw.githubusercontent.com/{repo_config['fork']}/inventory-schemas/"
        f"{repo_config['branch']}/schemas/system_profile/v1.yaml"
    )

    logger.info(f"Validating host against {repo_config['fork']}/{repo_config['branch']} schema...")
    return validate_host_list_against_spec(host_list, system_profile_spec)


def get_hosts_from_kafka_messages(consumer, topics, days):
    msgs = {}
    partitions = []
    parsed_hosts = []
    total_messages = 0
    seek_date = datetime.now() + timedelta(days=(-1 * days))

    for topic in topics:
        for partition_id in consumer.partitions_for_topic(topic):
            partitions.append(TopicPartition(topic, partition_id))

    consumer.assign(partitions)

    for tp in consumer.assignment():
        try:
            seek_position = consumer.offsets_for_times({tp: seek_date.timestamp() * 1000})[tp].offset
            consumer.seek(tp, seek_position)
        except AttributeError:
            logger.debug("No data in partition for the given date.")

    msgs = consumer.poll(timeout_ms=60000, max_records=10000)

    for topic_partition, messages in msgs.items():
        for message in messages:
            total_messages += 1
            try:
                parsed_message = json.loads(message.value)
                parsed_operation = OperationSchema(strict=True).load(parsed_message).data
                parsed_hosts.append(parsed_operation["data"])
            except json.JSONDecodeError:
                logger.exception(
                    "Unable to parse json message from message queue.", extra={"incoming_message": message}
                )
            except ValidationError:
                logger.exception("Could not parse operation.", extra={"parsed_message": parsed_message})

    if len(parsed_hosts) == 0:
        raise ValueError("No data available at the provided date.")

    logger.info(f"Parsed {len(parsed_hosts)} of {total_messages} hosts from message queue.")
    return parsed_hosts


def validate_sp_for_branch(consumer, topics, repo_fork="RedHatInsights", repo_branch="master", days=1):
    parsed_hosts = get_hosts_from_kafka_messages(consumer, topics, days)

    validation_results = {}
    for item in [{"fork": repo_fork, "branch": repo_branch}, {"fork": "RedHatInsights", "branch": "master"}]:
        validation_results[f"{item['fork']}/{item['branch']}"] = (
            _validate_host_list(parsed_hosts, item) if len(parsed_hosts) > 0 else {}
        )

    return validation_results
