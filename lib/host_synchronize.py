from kafka.errors import KafkaTimeoutError

from app.culling import Timestamps
from app.models import Host
from app.queue.event_producer import Topic
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.queue.queue import EGRESS_HOST_FIELDS
from app.serialization import serialize_host
from lib.metrics import synchronize_host_count

__all__ = ("synchronize_hosts",)


def synchronize_hosts(select_query, event_producer, chunk_size, config, interrupt=lambda: False):
    query = select_query.order_by(Host.id)
    host_list = query.limit(chunk_size).all()

    while len(host_list) > 0 and not interrupt():
        for host in host_list:
            serialized_host = serialize_host(host, Timestamps.from_config(config), EGRESS_HOST_FIELDS)
            event = build_event(EventType.updated, serialized_host)
            insights_id = host.canonical_facts.get("insights_id")
            headers = message_headers(EventType.updated, insights_id)
            # in case of a failed update event, event_producer logs the message.
            event_producer.write_event(event, str(serialized_host), headers, Topic.events)
            synchronize_host_count.inc()

            yield host.id

        try:
            # pace the events production speed as flush completes sending all buffered records.
            event_producer._kafka_producer.flush(300)
        except KafkaTimeoutError:
            raise KafkaTimeoutError(f"KafkaTimeoutError: failure to flush {chunk_size} records within 300 seconds")

        # load next chunk using keyset pagination
        host_list = query.filter(Host.id > host_list[-1].id).limit(chunk_size).all()
