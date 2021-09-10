# from kafka.errors import KafkaTimeoutError
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
duplicate_list = []


def unique(host_list):

    # traverse for all elements
    for host in host_list:
        # check if exists in unique_list or not
        if str(host.id) not in unique_list:
            unique_list.append(str(host.id))


def multiple_canonical_facts_host_query(host, canonical_facts):
    print("Entering multiple_canonical_facts_host_query")
    print(f"Canonical facts: {canonical_facts}")
    is_unique = False
    if host not in unique_list:
        if len(unique_list) > 0:
            print("Unique list has at least a host")
        else:
            unique_list.append(host)
            is_unique = True
    # check if any of the canonical_facts are similar
    if not is_unique:
        for fact in canonical_facts:
            for unique_host in unique_list:
                if fact in unique_host[1].keys():
                    print(f"Fact being checked: {fact}")
                    val = unique_host[1].get(fact)
                    if host[1][fact] == val:
                        print("this host is duplicate")
                        duplicate_list.append(host)
    return is_unique


def find_host_by_elevated_facts(host, all_hosts):
    canonical_facts = host[1]
    elevated_facts = {
        key: canonical_facts[key] for key in ELEVATED_CANONICAL_FACT_FIELDS if key in canonical_facts.keys()
    }
    if elevated_facts:
        elevated_keys = [key for key in ELEVATED_CANONICAL_FACT_FIELDS if key in canonical_facts.keys()]
        elevated_keys.reverse()

        for del_key in elevated_keys:
            existing_host = multiple_canonical_facts_host_query(host, elevated_facts)
            if existing_host:
                return existing_host

            del elevated_facts[del_key]

    return None


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

ELEVATED_CANONICAL_FACT_FIELDS = ("provider_id", "insights_id", "subscription_manager_id")


def delete_duplicate_hosts(select_query, event_producer, chunk_size, config, interrupt=lambda: False):
    query = select_query.order_by(Host.id)
    all_hosts = query.limit(chunk_size).all()

    host_count = 0
    for host in all_hosts:
        host_count += 1
        print(f"host counted: {host_count}")
        result = find_host_by_elevated_facts(host, all_hosts)
        if result:
            print(f"Host found: {host.id}")
            print(f"Unique hosts found: {len(unique_list)}"),
        print(f"Number of duplicate hosts found: {len(duplicate_list)}")
    # delete hosts which are not unique
    for host in all_hosts:
        if str(host[0]) not in unique_list:
            # delete this host
            print(f"Delete host: {host.id}")
        else:
            print(f"Host {str(host[0])} is unique!")
    # load next chunk using keyset pagination
    all_hosts = query.filter(Host.id > all_hosts[-1].id).limit(chunk_size).all()


# Starting code ####
# def delete_duplicate_hosts(select_query, event_producer, chunk_size, config, interrupt=lambda: False):
#     query = select_query.order_by(Host.id)
#     all_hosts = query.limit(chunk_size).all()

#     for cf in CANONICAL_FACTS:
#         query = select_query.order_by(Host.id).filter(Host.canonical_facts[cf].isnot(None))
#         # fq = query.filter(Host.canonical_facts['subscription_manager_id'].isnot(None))
#         host_list = query.limit(chunk_size).all()

#         print(f"Canonical fact: {cf}")
#         print(f"Total number of hosts in DB: {len(host_list)}")

#         print(f"Unique hosts found: {len(unique_list)}"),
#         if len(host_list) > 0 and not interrupt():
#             unique(host_list)
#             for host in host_list:
#                 yield host.id
#         try:
#             # pace the events production speed as flush completes sending all buffered records.
#             event_producer._kafka_producer.flush(300)
#         except KafkaTimeoutError:
#             raise KafkaTimeoutError(f"KafkaTimeoutError: failure to flush {chunk_size} records within 300 seconds")

#     # delete hosts which are not unique
#     for host in all_hosts:
#         if str(host[0]) not in unique_list:
#             # delete this host
#             print(f"Delete host: {host.id}")
#         else:
#             print(f"Host {str(host[0])} is unique!")
#     # load next chunk using keyset pagination
#     all_hosts = query.filter(Host.id > all_hosts[-1].id).limit(chunk_size).all()
