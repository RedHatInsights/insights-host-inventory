from copy import deepcopy

from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_

from app.auth.identity import AuthType
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.models import Host
from lib.metrics import delete_duplicate_host_count

# from app.logging import get_logger


# complete user identity
IDENTITY = {
    "account_number": "test",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {"email": "tuser@redhat.com", "first_name": "test"},
}

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
ALL_STALENESS_STATES = ("fresh", "stale", "stale_warning", "unknown")


def update_query_for_owner_id(identity, query):
    # kafka based requests have dummy identity for working around the identity requirement for CRUD operations
    # TODO: 'identity.auth_type is not 'classic-proxy' is a temporary fix. Remove when workaround is no longer needed
    print("identity auth type: %s", identity.auth_type)
    if identity and identity.identity_type == IdentityType.SYSTEM and identity.auth_type != AuthType.CLASSIC:
        return query.filter(and_(Host.system_profile_facts["owner_id"].as_string() == identity.system["cn"]))
    else:
        return query


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


def multiple_canonical_facts_host_query(identity, canonical_facts, query, restrict_to_owner_id=True):
    # query = Host.query.filter(
    query = query.filter(
        (Host.account == identity.account_number)
        & (contains_no_incorrect_facts_filter(canonical_facts))
        & (matches_at_least_one_canonical_fact_filter(canonical_facts))
    )
    if restrict_to_owner_id:
        query = update_query_for_owner_id(identity, query)
    return query


# Get hosts by the highest elevated canonical fact present
def find_host_by_multiple_elevated_canonical_facts(identity, canonical_facts, query):
    """
    First check if multiple hosts are returned.  If they are then retain by the highest
    priority elevated facts
    """
    print("find_host_by_multiple_elevated_canonical_facts(%s)", canonical_facts)

    if canonical_facts.get("provider_id"):
        if canonical_facts.get("subscription_manager_id"):
            canonical_facts.pop("subscription_manager_id")
        if canonical_facts.get("insights_id"):
            canonical_facts.pop("insights_id")
    elif canonical_facts.get("insights_id"):
        if canonical_facts.get("subscription_manager_id"):
            canonical_facts.pop("subscription_manager_id")

    hosts = (
        multiple_canonical_facts_host_query(identity, canonical_facts, query, restrict_to_owner_id=False)
        .order_by(Host.modified_on.desc())
        .all()
    )

    if hosts:
        print("Found existing host using canonical_fact match: %s", hosts)

    unique(hosts[0])


def trim_extra_facts(needed_fact, canonical_facts):
    for fact in CANONICAL_FACTS:
        if fact in canonical_facts and not fact == needed_fact:
            _ = canonical_facts.pop(fact)
    return canonical_facts


def find_host_by_multiple_canonical_facts(identity, canonical_facts, query):
    """
    Returns first match for a host containing given canonical facts
    """
    print("find_host_by_multiple_canonical_facts(%s)", canonical_facts)

    for fact in canonical_facts:
        needed_cf = trim_extra_facts(fact, deepcopy(canonical_facts))
        hosts = (
            multiple_canonical_facts_host_query(identity, needed_cf, query, restrict_to_owner_id=False)
            .order_by(Host.modified_on.desc())
            .all()
        )

        unique(hosts[0])

        if hosts:
            print("Found existing host using canonical_fact match: %s", hosts)


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


def delete_duplicate_hosts(select_query, event_producer, chunk_size, config, interrupt=lambda: False):
    identity = Identity(IDENTITY)

    query = select_query
    all_hosts = query.limit(chunk_size).all()

    for host in all_hosts:
        print(f"Canonical facts: {host.canonical_facts}")
        elevated_facts = get_elevated_canonical_facts(host.canonical_facts)
        print(f"elevated canonical facts: {elevated_facts}")
        if elevated_facts:
            find_host_by_multiple_elevated_canonical_facts(identity, elevated_facts, query)
        else:
            unelevated_facts = get_unelevated_canonical_facts(host.canonical_facts)
            print(f"unelevated canonical facts: {unelevated_facts}")
            if unelevated_facts:
                find_host_by_multiple_canonical_facts(identity, unelevated_facts, query)

        print(f"Unique hosts count: {len(unique_list)}")
        print(f"All hosts count: {len(all_hosts)}")

    for host in all_hosts:
        hostIdAccount = {"id": host.id, "account": host.account}
        if hostIdAccount not in unique_list:
            print(f"Duplicate host: {host.id}")
            print(f"Duplicate canonical_facts: {host.canonical_facts}")
            duplicate_list.append(hostIdAccount)
    print(f"Duplicate hosts count: {len(duplicate_list)}")

    # delete duplicate hosts
    while len(duplicate_list) > 0 and not interrupt():
        for host in duplicate_list:
            _delete_host(query, host)
            duplicate_list.remove(host)
            delete_duplicate_host_count.inc()

            yield host["id"]
        print("Done deleting duplicate hosts!!!")
