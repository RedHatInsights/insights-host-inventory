from sqlalchemy.orm.base import instance_state

from app.logging import get_logger
from app.models import Host
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from lib.host_kafka import kafka_available
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time

__all__ = ("delete_hosts",)
logger = get_logger(__name__)


def delete_hosts(select_query, event_producer, chunk_size, interrupt=lambda: False):
    while select_query.count():
        for host in select_query.limit(chunk_size):
            host_id = host.id
            with delete_host_processing_time.time():
                host_deleted = _delete_host(select_query.session, event_producer, host)

            yield host_id, host_deleted

            if interrupt():
                return


def _delete_host(session, event_producer, host):
    delete_query = session.query(Host).filter(Host.id == host.id)
    if kafka_available():
        delete_query.delete(synchronize_session="fetch")
        host_deleted = _deleted_by_this_query(host)
        if host_deleted:
            delete_host_count.inc()
            event = build_event(EventType.delete, host)
            insights_id = host.canonical_facts.get("insights_id")
            headers = message_headers(EventType.delete, insights_id)
            event_producer.write_event(event, str(host.id), headers, wait=True)
            delete_query.session.commit()
            return host_deleted
        else:
            delete_query.session.rollback()
            return host_deleted
    else:
        logger.error(f"host with {host.id} NOT deleted because Kafka server not available.")
        return False


def _deleted_by_this_query(host):
    # Before committing the change, verify that the host has been marked 'expired'
    return not instance_state(host).expired
