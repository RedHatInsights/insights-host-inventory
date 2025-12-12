from confluent_kafka.error import KafkaException
from confluent_kafka.error import ProduceError

from app.culling import Timestamps
from app.logging import get_logger
from app.models import Host
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.serialization import serialize_group_without_host_count
from app.serialization import serialize_host
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness
from lib.group_repository import get_group_using_host_id
from lib.metrics import synchronize_host_count

logger = get_logger(__name__)

__all__ = ("synchronize_hosts", "sync_group_data")


def synchronize_hosts(
    select_hosts_query, select_staleness_query, event_producer, chunk_size, config, interrupt=lambda: False
):
    num_synchronized = 0
    custom_staleness_dict = {
        staleness.org_id: serialize_staleness_to_dict(staleness) for staleness in select_staleness_query.all()
    }

    # Get all distinct org_ids from the base query
    org_ids_query = select_hosts_query.with_entities(Host.org_id).distinct().order_by(Host.org_id)

    for (org_id,) in org_ids_query:
        if interrupt():
            break

        logger.info(f"Synchronizing hosts for org_id: {org_id}")
        org_synchronized = _synchronize_hosts_for_org(
            select_hosts_query.filter(Host.org_id == org_id),
            custom_staleness_dict,
            event_producer,
            chunk_size,
            config,
            interrupt,
        )
        num_synchronized += org_synchronized
        logger.info(f"Completed org_id {org_id}: {org_synchronized} hosts synchronized")

    return num_synchronized


def _synchronize_hosts_for_org(org_hosts_query, custom_staleness_dict, event_producer, chunk_size, config, interrupt):
    query = org_hosts_query.order_by(Host.id)
    host_list = query.limit(chunk_size).all()
    num_synchronized = 0

    while len(host_list) > 0 and not interrupt():
        for host in host_list:
            staleness = None
            try:
                staleness = custom_staleness_dict[host.org_id]
            except KeyError:
                staleness = get_sys_default_staleness(config)

            serialized_host = serialize_host(host, Timestamps.from_config(config), staleness=staleness)
            event = build_event(EventType.updated, serialized_host)
            headers = message_headers(
                EventType.updated,
                host.get("insights_id"),
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

        # load next chunk using keyset pagination within the same org_id partition
        host_list = query.filter(Host.id > host_list[-1].id).limit(chunk_size).all()

    return num_synchronized


def sync_group_data(session, chunk_size, interrupt=lambda: False):
    num_updated = 0
    num_failed = 0

    # Get all distinct org_ids that have hosts with empty groups
    org_ids_query = session.query(Host.org_id).filter(Host.groups == []).distinct().order_by(Host.org_id)

    for (org_id,) in org_ids_query:
        if interrupt():
            break

        logger.info(f"Processing org_id: {org_id}")
        org_updated, org_failed = _sync_group_data_for_org(session, org_id, chunk_size, interrupt)
        num_updated += org_updated
        num_failed += org_failed
        logger.info(f"Completed org_id {org_id}: {org_updated} updated, {org_failed} failed")

    return num_updated, num_failed


def _sync_group_data_for_org(session, org_id, chunk_size, interrupt):
    query = session.query(Host).filter(Host.org_id == org_id, Host.groups == []).order_by(Host.id)
    host_list = query.limit(chunk_size).all()
    num_updated = 0
    num_failed = 0

    while len(host_list) > 0 and not interrupt():
        logger.info(f"Processing batch of {len(host_list)} hosts for org_id {org_id}")
        num_in_current_batch = 0

        for host in host_list:
            # If host.groups says it's empty,
            # Get the host's associated Group (if any) and store it in the "groups" field
            if host.groups is None:
                host.groups = []

            group = get_group_using_host_id(str(host.id), host.org_id)
            if host.groups == [] and group:
                host.groups = [serialize_group_without_host_count(group)]
                session.add(host)
                num_in_current_batch += 1

        # commit changes, and then load next chunk using keyset pagination
        try:
            session.commit()
            num_updated += num_in_current_batch
            logger.info(
                f"{num_in_current_batch} changes flushed for org_id {org_id}; "
                f"{num_updated} updated so far for this org."
            )
        except Exception as exc:
            logger.exception(f"Failed to sync host.groups data for batch in org_id {org_id}.", exc_info=exc)
            num_failed += len(host_list)

        host_list = query.filter(Host.id > host_list[-1].id).limit(chunk_size).all()

    return num_updated, num_failed
