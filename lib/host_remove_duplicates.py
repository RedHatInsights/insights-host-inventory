from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_

from app.models import Host
from lib.metrics import delete_duplicate_host_count

__all__ = ("delete_duplicate_hosts",)

# The order is important, particularly the first 3 which are elevated facts with provider_id being the highest priority
CANONICAL_FACTS = ("fqdn", "satellite_id", "bios_uuid", "ip_addresses", "mac_addresses")

ELEVATED_CANONICAL_FACT_FIELDS = ("provider_id", "insights_id", "subscription_manager_id")


def matches_at_least_one_canonical_fact_filter(canonical_facts):
    # Contains at least one correct CF value
    # Correct value = contains key:value
    # -> OR( *correct values )
    return or_(Host.canonical_facts.contains({key: value}) for key, value in canonical_facts.items())


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
def find_host_by_elevated_canonical_facts(elevated_cfs, query, logger):
    """
    First check if multiple hosts are returned.  If they are then retain the one with the highest
    priority elevated fact
    """
    logger.debug("find_host_by_elevated_canonical_facts(%s)", elevated_cfs)

    if elevated_cfs.get("provider_id"):
        elevated_cfs.pop("subscription_manager_id", None)
        elevated_cfs.pop("insights_id", None)
    elif elevated_cfs.get("insights_id"):
        elevated_cfs.pop("subscription_manager_id", None)

    host = multiple_canonical_facts_host_query(elevated_cfs, query).order_by(Host.modified_on.desc()).one_or_none()

    if host:
        logger.debug("Found existing host using canonical_fact match")

    return host


# this function is called when no elevated canonical facts are present in the host
def find_host_by_regular_canonical_facts(canonical_facts, query, logger):
    """
    Returns all matches for a host containing given canonical facts
    """
    logger.debug("find_host_by_regular_canonical_facts(%s)", canonical_facts)

    host = multiple_canonical_facts_host_query(canonical_facts, query).order_by(Host.modified_on.desc()).one_or_none()

    if host:
        logger.debug("Found existing host using canonical_fact match")

    return host


def get_elevated_canonical_facts(canonical_facts):
    elevated_facts = {key: canonical_facts[key] for key in ELEVATED_CANONICAL_FACT_FIELDS if key in canonical_facts}
    return elevated_facts


def get_regular_canonical_facts(canonical_facts):
    regular_cfs = {key: canonical_facts[key] for key in CANONICAL_FACTS if key in canonical_facts}
    return regular_cfs


def _delete_host(query, host):
    delete_query = query.filter(Host.id == str(host["id"]))
    delete_query.delete(synchronize_session="fetch")
    delete_query.session.commit()


def delete_duplicate_hosts(select_query, chunk_size, logger, interrupt=lambda: False):
    query = select_query
    logger.info(f"Total number of hosts in inventory: {query.count()}")

    distinct_accounts = [row.account for row in query.distinct(Host.account).limit(chunk_size).all()]
    logger.info(f"Total number of accounts in inventory: {len(distinct_accounts)}")

    for account in distinct_accounts:
        # set uniquess within the account
        unique_list = []

        def unique(host):
            if host.id not in unique_list:
                unique_list.append(host.id)

        acct_query = query.filter(Host.account == account)
        host_list = acct_query.limit(chunk_size).all()
        for host in host_list:
            logger.info(f"Host ID: {host.id}")
            logger.info(f"Canonical facts: {host.canonical_facts}")
            elevated_cfs = get_elevated_canonical_facts(host.canonical_facts)
            logger.info(f"elevated canonical facts: {elevated_cfs}")
            if elevated_cfs:
                host_match = find_host_by_elevated_canonical_facts(elevated_cfs, acct_query, logger)
            else:
                regular_cfs = get_regular_canonical_facts(host.canonical_facts)
                logger.info(f"regular canonical facts: {regular_cfs}")
                if regular_cfs:
                    host_match = find_host_by_regular_canonical_facts(regular_cfs, acct_query, logger)

            unique(host_match)
            logger.info(f"Unique hosts count: {len(unique_list)}")
            logger.info(f"All hosts count: {len(host_list)}")

        duplicate_list = []
        for matching_host in host_list:
            # TODO: Review this logic.
            # I made a fix here, and I don't think this conditional makes sense.
            if matching_host.id not in unique_list:
                duplicate_list.append(matching_host.id)
        logger.info(f"Duplicate hosts count: {len(duplicate_list)}")

        # delete duplicate hosts
        while len(duplicate_list) > 0 and not interrupt():
            for host in duplicate_list:
                _delete_host(query, host)
                duplicate_list.remove(host)
                delete_duplicate_host_count.inc()

                yield host["id"]
                # load next chunk using keyset pagination
        host_list = query.filter(Host.id > host_list[-1].id).limit(chunk_size).all()

    logger.info("Done deleting duplicate hosts!")
