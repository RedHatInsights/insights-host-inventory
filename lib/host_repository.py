from enum import Enum

from sqlalchemy import and_
from sqlalchemy import or_

from app import inventory_config
from app.culling import staleness_to_conditions
from app.logging import get_logger
from app.models import db
from app.models import Host
from app.serialization import DEFAULT_FIELDS
from app.serialization import serialize_host
from lib import metrics
from lib.db import session_guard

__all__ = (
    "add_host",
    "canonical_fact_host_query",
    "canonical_facts_host_query",
    "create_new_host",
    "find_existing_host",
    "find_host_by_canonical_facts",
    "find_hosts_by_staleness",
    "find_non_culled_hosts",
    "stale_timestamp_filter",
    "update_existing_host",
)

AddHostResult = Enum("AddHostResult", ("created", "updated"))

# These are the "elevated" canonical facts that are
# given priority in the host deduplication process.
# NOTE: The order of this tuple is important.  The order defines
# the priority.
ELEVATED_CANONICAL_FACT_FIELDS = ("insights_id", "subscription_manager_id")

ALL_STALENESS_STATES = ("fresh", "stale", "stale_warning", "unknown")
NULL = None

logger = get_logger(__name__)


def add_host(input_host, staleness_offset, update_system_profile=True, fields=DEFAULT_FIELDS):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """

    with session_guard(db.session):
        existing_host = find_existing_host(input_host.account, input_host.canonical_facts)
        if existing_host:
            return update_existing_host(existing_host, input_host, staleness_offset, update_system_profile, fields)
        else:
            return create_new_host(input_host, staleness_offset, fields)


@metrics.host_dedup_processing_time.time()
def find_existing_host(account_number, canonical_facts):
    existing_host = _find_host_by_elevated_ids(account_number, canonical_facts)

    if not existing_host:
        existing_host = find_host_by_canonical_facts(account_number, canonical_facts)

    return existing_host


@metrics.find_host_using_elevated_ids.time()
def _find_host_by_elevated_ids(account_number, canonical_facts):
    for elevated_cf_name in ELEVATED_CANONICAL_FACT_FIELDS:
        cf_value = canonical_facts.get(elevated_cf_name)
        if cf_value:
            existing_host = find_host_by_canonical_fact(account_number, elevated_cf_name, cf_value)
            if existing_host:
                return existing_host

    return None


def canonical_fact_host_query(account_number, canonical_fact, value):
    query = Host.query.filter(
        (Host.account == account_number) & (Host.canonical_facts[canonical_fact].astext == value)
    )
    return find_non_culled_hosts(query)


def canonical_facts_host_query(account_number, canonical_facts):
    query = Host.query.filter(
        (Host.account == account_number)
        & (
            Host.canonical_facts.comparator.contains(canonical_facts)
            | Host.canonical_facts.comparator.contained_by(canonical_facts)
        )
    )
    return find_non_culled_hosts(query)


def find_host_by_canonical_fact(account_number, canonical_fact, value):
    """
    Returns first match for a host containing given canonical facts
    """
    logger.debug("find_host_by_canonical_fact(%s, %s)", canonical_fact, value)

    host = canonical_fact_host_query(account_number, canonical_fact, value).first()

    if host:
        logger.debug("Found existing host using canonical_fact match: %s", host)

    return host


def find_host_by_canonical_facts(account_number, canonical_facts):
    """
    Returns first match for a host containing given canonical facts
    """
    logger.debug("find_host_by_canonical_facts(%s)", canonical_facts)

    host = canonical_facts_host_query(account_number, canonical_facts).first()

    if host:
        logger.debug("Found existing host using canonical_fact match: %s", host)

    return host


def find_hosts_by_staleness(staleness, query):
    logger.debug("find_hosts_by_staleness(%s)", staleness)
    config = inventory_config()
    staleness_conditions = tuple(staleness_to_conditions(config, staleness, stale_timestamp_filter))
    if "unknown" in staleness:
        staleness_conditions += (Host.stale_timestamp == NULL,)

    return query.filter(or_(*staleness_conditions))


def find_non_culled_hosts(query):
    return find_hosts_by_staleness(ALL_STALENESS_STATES, query)


@metrics.new_host_commit_processing_time.time()
def create_new_host(input_host, staleness_offset, fields):
    logger.debug("Creating a new host")
    input_host.save()
    db.session.commit()
    metrics.create_host_count.inc()
    logger.debug("Created host:%s", input_host)
    return serialize_host(input_host, staleness_offset, fields), AddHostResult.created


@metrics.update_host_commit_processing_time.time()
def update_existing_host(existing_host, input_host, staleness_offset, update_system_profile, fields):
    logger.debug("Updating an existing host")
    logger.debug(f"existing host = {existing_host}")
    existing_host.update(input_host, update_system_profile)
    db.session.commit()
    metrics.update_host_count.inc()
    logger.debug("Updated host:%s", existing_host)
    return serialize_host(existing_host, staleness_offset, fields), AddHostResult.updated


def stale_timestamp_filter(gt=None, lte=None):
    filter_ = ()
    if gt:
        filter_ += (Host.stale_timestamp > gt,)
    if lte:
        filter_ += (Host.stale_timestamp <= lte,)
    return and_(*filter_)
