from copy import deepcopy

from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_

from app.models import Host
from lib.metrics import delete_duplicate_host_count

# from app.logging import get_logger

# logger = None

__all__ = ("delete_duplicate_hosts",)

# initialize a empty lists
unique_list = []
duplicate_list = []


def unique(host):
    # Use id and account to create unique hosts across all accounts.
    unique_host = {"id": host.id, "account": host.account}
    if unique_host not in unique_list:
        unique_list.append(unique_host)


# The order is important, particularly the first 3 which are elevated facts with provider_id being the highest priority
CANONICAL_FACTS = ("fqdn", "satellite_id", "bios_uuid", "ip_addresses", "mac_addresses")

ELEVATED_CANONICAL_FACT_FIELDS = ("provider_id", "insights_id", "subscription_manager_id")


def matches_at_least_one_canonical_fact_filter(canonical_facts):
    # Contains at least one correct CF value
    # Correct value = contains key:value
    # -> OR( *correct values )
    filter_ = ()
    for key, value in canonical_facts.items():
        filter_ += (Host.canonical_facts.contains({key: value}),)

    return or_(*filter_)


def contains_no_incorrect_facts_filter(canonical_facts):
    # Does not contain any incorrect CF values
    # Incorrect value = AND( key exists, NOT( contains key:value ) )
    # -> NOT( OR( *Incorrect values ) )
    filter_ = ()
    for key, value in canonical_facts.items():
        filter_ += (
            and_(Host.canonical_facts.has_key(key), not_(Host.canonical_facts.contains({key: value}))),  # noqa: W601
        )

    return not_(or_(*filter_))


def multiple_canonical_facts_host_query(canonical_facts, query):
    query = query.filter(
        (contains_no_incorrect_facts_filter(canonical_facts))
        & (matches_at_least_one_canonical_fact_filter(canonical_facts))
    )
    return query


# Get hosts by the highest elevated canonical fact present
def find_host_by_multiple_elevated_canonical_facts(canonical_facts, query, logger):
    """
    First check if multiple hosts are returned.  If they are then retain the with the highest
    priority elevated fact
    """
    logger.debug("find_host_by_multiple_elevated_canonical_facts(%s)", canonical_facts)

    if canonical_facts.get("provider_id"):
        if canonical_facts.get("subscription_manager_id"):
            canonical_facts.pop("subscription_manager_id")
        if canonical_facts.get("insights_id"):
            canonical_facts.pop("insights_id")
    elif canonical_facts.get("insights_id"):
        if canonical_facts.get("subscription_manager_id"):
            canonical_facts.pop("subscription_manager_id")

    hosts = multiple_canonical_facts_host_query(canonical_facts, query).order_by(Host.modified_on.desc()).all()

    if hosts:
        logger.debug("Found existing host using canonical_fact match: %s", hosts)

    unique(hosts[0])


def trim_extra_facts(needed_fact, canonical_facts):
    for fact in CANONICAL_FACTS:
        if fact in canonical_facts and not fact == needed_fact:
            _ = canonical_facts.pop(fact)
    return canonical_facts


# this function is called when no elevated canonical facts are present in the host
def find_host_by_multiple_canonical_facts(canonical_facts, query, logger):
    """
    Returns all matches for a host containing given canonical facts
    """
    logger.debug("find_host_by_multiple_canonical_facts(%s)", canonical_facts)

    for fact in canonical_facts:
        needed_cf = trim_extra_facts(fact, deepcopy(canonical_facts))
        hosts = multiple_canonical_facts_host_query(needed_cf, query).order_by(Host.modified_on.desc()).all()

        unique(hosts[0])

        if hosts:
            logger.debug("Found existing host using canonical_fact match: %s", hosts)


def get_elevated_canonical_facts(canonical_facts):
    elevated_facts = {
        key: canonical_facts[key] for key in ELEVATED_CANONICAL_FACT_FIELDS if key in canonical_facts.keys()
    }
    return elevated_facts


def get_unelevated_canonical_facts(canonical_facts):
    unelevated_facts = {key: canonical_facts[key] for key in CANONICAL_FACTS if key in canonical_facts.keys()}
    return unelevated_facts


def _delete_host(query, host):
    delete_query = query.filter(Host.id == host["id"].hex)
    delete_query.delete(synchronize_session="fetch")
    delete_query.session.commit()


def delete_duplicate_hosts(select_query, chunk_size, logger, interrupt=lambda: False):
    query = select_query
    all_hosts = query.limit(chunk_size).all()

    for host in all_hosts:
        logger.info(f"Host ID: {host.id}")
        logger.info(f"Canonical facts: {host.canonical_facts}")
        elevated_facts = get_elevated_canonical_facts(host.canonical_facts)
        logger.info(f"elevated canonical facts: {elevated_facts}")
        if elevated_facts:
            find_host_by_multiple_elevated_canonical_facts(elevated_facts, query, logger)
        else:
            unelevated_facts = get_unelevated_canonical_facts(host.canonical_facts)
            logger.info(f"unelevated canonical facts: {unelevated_facts}")
            if unelevated_facts:
                find_host_by_multiple_canonical_facts(unelevated_facts, query, logger)

        logger.info(f"Unique hosts count: {len(unique_list)}")
        logger.info(f"All hosts count: {len(all_hosts)}")

    for host in all_hosts:
        hostIdAccount = {"id": host.id, "account": host.account}
        if hostIdAccount not in unique_list:
            duplicate_list.append(hostIdAccount)
    logger.info(f"Duplicate hosts count: {len(duplicate_list)}")

    # delete duplicate hosts
    while len(duplicate_list) > 0 and not interrupt():
        for host in duplicate_list:
            _delete_host(query, host)
            duplicate_list.remove(host)
            delete_duplicate_host_count.inc()

            yield host["id"]
        logger.info("Done deleting duplicate hosts!!!")
