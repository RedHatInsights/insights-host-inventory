from kafka.errors import KafkaTimeoutError

from app.models import Host

# from lib.host_repository import ELEVATED_CANONICAL_FACT_FIELDS as ecff

# from lib.metrics import synchronize_host_count

# from app.culling import Timestamps
# from app.queue.events import build_event
# from app.queue.events import EventType
# from app.queue.events import message_headers
# from app.queue.queue import EGRESS_HOST_FIELDS
# from app.serialization import serialize_host

__all__ = ("delete_duplicate_hosts",)

# initialize a null list
unique_list = []


def unique(host_list):

    # traverse for all elements
    for host in host_list:
        # check if exists in unique_list or not
        if str(host.id) not in unique_list:
            unique_list.append(str(host.id))


# The order is important, particularly the first 3 which are elevated facts with provider_id being the highest priority
CANONICAL_FACTS = (
    "provider_id",
    "insights_id",
    "subscription_manager_id",
    "fqdn",
    "satellite_id",
    "bios_uuid",
    "ip_addresses",
    "mac_addresses",
)


def delete_duplicate_hosts(select_query, event_producer, chunk_size, config, interrupt=lambda: False):
    query = select_query.order_by(Host.id)
    all_hosts = query.limit(chunk_size).all()

    for cf in CANONICAL_FACTS:
        query = select_query.order_by(Host.id).filter(Host.canonical_facts[cf].isnot(None))
        # fq = query.filter(Host.canonical_facts['subscription_manager_id'].isnot(None))
        host_list = query.limit(chunk_size).all()

        print(f"Canonical fact: {cf}")
        print(f"Total number of hosts in DB: {len(host_list)}")

        print(f"Unique hosts found: {len(unique_list)}"),
        if len(host_list) > 0 and not interrupt():
            unique(host_list)
            for host in host_list:
                yield host.id
        try:
            # pace the events production speed as flush completes sending all buffered records.
            event_producer._kafka_producer.flush(300)
        except KafkaTimeoutError:
            raise KafkaTimeoutError(f"KafkaTimeoutError: failure to flush {chunk_size} records within 300 seconds")

    # delete hosts which are not unique
    for host in all_hosts:
        if str(host[0]) not in unique_list:
            # delete this host
            print(f"Delete host: {host.id}")
        else:
            print(f"Host {str(host[0])} is unique!")
    # load next chunk using keyset pagination
    all_hosts = query.filter(Host.id > all_hosts[-1].id).limit(chunk_size).all()
