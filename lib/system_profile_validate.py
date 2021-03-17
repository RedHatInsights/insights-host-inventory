import json
from datetime import datetime
from datetime import timedelta

from kafka.common import TopicPartition
from marshmallow import ValidationError
from requests import get
from yaml import safe_load

from app.exceptions import InventoryException
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


def get_schema(fork, branch):
    return get_schema_from_url(
        f"https://raw.githubusercontent.com/{fork}/inventory-schemas/" f"{branch}/schemas/system_profile/v1.yaml"
    )


def validate_sp_schemas(consumer, topics, schemas, days=1, max_messages=10000):
    total_message_count = 0
    partitions = []
    test_results = {branch: {} for branch in schemas.keys()}
    seek_date = datetime.now() + timedelta(days=(-1 * days))

    logger.info("Validating messages from these topics:")

    for topic in topics:
        logger.info(topic)
        for partition_id in consumer.partitions_for_topic(topic) or []:
            partitions.append(TopicPartition(topic, partition_id))

    consumer.assign(partitions)
    partitions = consumer.assignment()

    start_offsets = consumer.offsets_for_times({tp: seek_date.timestamp() * 1000 for tp in partitions})
    end_offsets = consumer.end_offsets(partitions)

    for tp in partitions:
        try:
            consumer.seek(tp, start_offsets[tp].offset)
        except AttributeError:
            logger.debug("No data in partition for the given date.")

    logger.info("Beginning validation...")

    while total_message_count < max_messages:
        new_message_count = 0
        for partition, partition_messages in consumer.poll(timeout_ms=60000, max_records=500).items():
            if consumer.position(partition) >= end_offsets[partition]:
                continue

            new_message_count += len(partition_messages)
            logger.info(f"Polled {new_message_count} messages from the queue.")

            for message in partition_messages:
                try:
                    host = OperationSchema(strict=True).load(json.loads(message.value)).data["data"]
                    if not host.get("reporter"):
                        host["reporter"] = "unknown_reporter"
                    for branch, sp_spec in schemas.items():
                        if host["reporter"] not in test_results[branch].keys():
                            test_results[branch][host["reporter"]] = TestResult()
                        try:
                            deserialize_host(host, system_profile_spec=sp_spec)
                            test_results[branch][host["reporter"]].pass_count += 1
                        except InventoryException as ie:
                            test_results[branch][host["reporter"]].fail_count += 1
                            logger.info(f"Message failed validation: {ie.detail}")
                        except Exception as e:
                            logger.info(f"Message caused an unexpected exception: {e}")
                except json.JSONDecodeError:
                    logger.exception("Unable to parse json message from message queue.")
                except ValidationError:
                    logger.exception("Unable to parse operation from message.")

        if new_message_count == 0:
            break

        total_message_count += new_message_count
        logger.info(f"{total_message_count} messages processed so far, out of a maximum {max_messages}.")

    if total_message_count == 0:
        raise ValueError("No data available at the provided date.")

    logger.info("Validation complete.")

    return test_results


def validate_sp_for_branch(
    consumer, topics, repo_fork="RedHatInsights", repo_branch="master", days=1, max_messages=10000
):
    schemas = {"RedHatInsights/master": get_schema("RedHatInsights", "master")}

    schemas[f"{repo_fork}/{repo_branch}"] = get_schema(repo_fork, repo_branch)

    return validate_sp_schemas(consumer, topics, schemas, days, max_messages)
