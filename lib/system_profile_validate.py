import json
from datetime import datetime
from datetime import timedelta

from confluent_kafka import Consumer
from confluent_kafka import TopicPartition
from marshmallow import ValidationError
from requests import get
from yaml import safe_load

from app.exceptions import InventoryException
from app.logging import get_logger
from app.queue.host_mq import HostOperationSchema
from app.serialization import deserialize_host

__all__ = ("validate_sp_for_branch",)

logger = get_logger(__name__)


class TestResult:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0


def get_schema_from_url(url: str) -> dict:
    response = get(url)
    if response.status_code != 200:
        raise ValueError(f"Schema not found at URL: {url}")
    return safe_load(get(url).content.decode("utf-8"))


def get_schema(fork: str, branch: str) -> dict:
    return get_schema_from_url(
        f"https://raw.githubusercontent.com/{fork}/inventory-schemas/{branch}/schemas/system_profile/v1.yaml"
    )


def validate_sp_schemas(
    consumer: Consumer, topics: list[str], schemas: dict, days: int = 1, max_messages: int = 10000
) -> dict[str, dict[str, TestResult]]:
    total_message_count = 0
    test_results: dict[str, dict[str, TestResult]] = {branch: {} for branch in schemas.keys()}
    seek_date = datetime.now() + timedelta(days=(-1 * days))

    logger.info("Validating messages from these topics:")
    partitions = []
    for topic_name in topics:
        logger.info(topic_name)
        filtered_topics = consumer.list_topics(topic_name)
        partitions_dict = filtered_topics.topics[topic_name].partitions
        for partition_id in partitions_dict.keys():
            partitions.append(TopicPartition(topic_name, partition_id, int(seek_date.timestamp()) * 1000))

    consumer.assign(partitions)
    partitions = consumer.assignment()

    start_offsets = consumer.offsets_for_times(partitions)

    for tp in start_offsets:
        try:
            consumer.seek(tp)
        except AttributeError:
            logger.debug("No data in partition for the given date.")

    logger.info("Beginning validation...")

    while total_message_count < max_messages:
        new_messages = consumer.consume(timeout=10)
        new_message_count = len(new_messages)
        logger.info(f"Consumed {new_message_count} messages from the queue.")

        for message in new_messages:
            try:
                host = HostOperationSchema().load(json.loads(message.value()))["data"]
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
    consumer: Consumer,
    topics: list[str],
    repo_fork: str = "RedHatInsights",
    repo_branch: str = "master",
    days: int = 1,
    max_messages: int = 10000,
) -> dict[str, dict[str, TestResult]]:
    schemas = {"RedHatInsights/master": get_schema("RedHatInsights", "master")}

    schemas[f"{repo_fork}/{repo_branch}"] = get_schema(repo_fork, repo_branch)

    return validate_sp_schemas(consumer, topics, schemas, days, max_messages)
