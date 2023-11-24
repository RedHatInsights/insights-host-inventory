from confluent_kafka.error import ProduceError

from app.culling import Timestamps
from app.logging import get_logger
from app.models import Host
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.serialization import serialize_host
from lib.metrics import synchronize_host_count

logger = get_logger(__name__)

__all__ = ("synchronize_hosts",)


def synchronize_hosts(select_query, event_producer, chunk_size, config, interrupt=lambda: False):
    query = select_query.order_by(Host.id)
    host_list = query.limit(chunk_size).all()
    num_synchronized = 0

    while len(host_list) > 0 and not interrupt():
        for host in host_list:
            # First, set host.groups to [] if it's null.
            if host.groups is None:
                host.groups = []

            serialized_host = serialize_host(host, Timestamps.from_config(config))
            event = build_event(EventType.updated, serialized_host)
            headers = message_headers(
                EventType.updated,
                host.canonical_facts.get("insights_id"),
                host.reporter,
                host.system_profile_facts.get("host_type"),
                host.system_profile_facts.get("operating_system", {}).get("name"),
            )
            # in case of a failed update event, event_producer logs the message.
            event_producer.write_event(event, str(host.id), headers, wait=True)
            synchronize_host_count.inc()
            logger.info("Synchronized host: %s", str(host.id))

            num_synchronized += 1

        try:
            # pace the events production speed as flush completes sending all buffered records.
            event_producer._kafka_producer.flush(300)
        except ProduceError:
            raise ProduceError(f"ProduceError: Kafka failure to flush {chunk_size} records within 300 seconds")

        # flush changes, and then load next chunk using keyset pagination
        query.session.flush()
        host_list = query.filter(Host.id > host_list[-1].id).limit(chunk_size).all()

    return num_synchronized
