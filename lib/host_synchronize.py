from confluent_kafka.error import KafkaException
from confluent_kafka.error import ProduceError

from app.culling import Timestamps
from app.logging import get_logger
from app.models import Host
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.serialization import serialize_host
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness
from lib.group_repository import get_group_using_host_id
from lib.metrics import synchronize_host_count

logger = get_logger(__name__)

__all__ = ("synchronize_hosts",)


def synchronize_hosts(
    select_hosts_query, select_staleness_query, event_producer, chunk_size, config, interrupt=lambda: False
):
    query = select_hosts_query.order_by(Host.id)
    host_list = query.limit(chunk_size).all()
    num_synchronized = 0
    custom_staleness_dict = {
        staleness.org_id: serialize_staleness_to_dict(staleness) for staleness in select_staleness_query.all()
    }

    while len(host_list) > 0 and not interrupt():
        for host in host_list:
            # First, set host.groups to [] if it's null.
            if host.groups is None:
                host.groups = []

            # This is a temporary fix that we can remove later.
            # If host.groups says it's empty,
            # Get the host's associated Group (if any) and store it in the "groups" field
            if host.groups == [] and (group := get_group_using_host_id(str(host.id), host.org_id)):
                host.groups = [{"id": str(group.id), "name": group.name, "ungrouped": group.ungrouped}]

            staleness = None
            try:
                staleness = custom_staleness_dict[host.org_id]
            except KeyError:
                staleness = get_sys_default_staleness(config)

            serialized_host = serialize_host(host, Timestamps.from_config(config), staleness=staleness)
            event = build_event(EventType.updated, serialized_host)
            headers = message_headers(
                EventType.updated,
                host.canonical_facts.get("insights_id"),
                host.reporter,
                host.system_profile_facts.get("host_type"),
                host.system_profile_facts.get("operating_system", {}).get("name"),
                str(host.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
            )
            # in case of a failed update event, event_producer logs the message.
            # Workaround to solve: https://issues.redhat.com/browse/RHINENG-4856
            try:
                event_producer.write_event(event, str(host.id), headers, wait=True)
                synchronize_host_count.inc()
                logger.info("Synchronized host: %s", str(host.id))

                num_synchronized += 1
            except (ProduceError, KafkaException):
                logger.error(f"Failed to synchronize host: {str(host.id)} because of {ProduceError.code}")
                continue

        try:
            # pace the events production speed as flush completes sending all buffered records.
            event_producer._kafka_producer.flush(300)
        except ProduceError as e:
            raise ProduceError(f"ProduceError: Kafka failure to flush {chunk_size} records within 300 seconds") from e

        # flush changes, and then load next chunk using keyset pagination
        query.session.flush()
        host_list = query.filter(Host.id > host_list[-1].id).limit(chunk_size).all()

    return num_synchronized
