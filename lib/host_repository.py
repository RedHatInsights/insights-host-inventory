from enum import Enum

from sqlalchemy import and_

from app.logging import get_logger
from app.models import db
from app.models import Host
from app.serialization import serialize_host
from lib import metrics
from lib.db import session_guard

__all__ = (
    "add_host",
    "canonical_facts_host_query",
    "create_new_host",
    "find_existing_host",
    "find_host_by_canonical_facts",
    "stale_timestamp_filter",
    "update_existing_host",
)

# FIXME:  rename this
AddHostResults = Enum("AddHostResults", ["created", "updated"])

# These are the "elevated" canonical facts that are
# given priority in the host deduplication process.
# NOTE: The order of this tuple is important.  The order defines
# the priority.
ELEVATED_CANONICAL_FACT_FIELDS = ("insights_id", "subscription_manager_id")

logger = get_logger(__name__)


def add_host(input_host, staleness_offset, update_system_profile=True):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """

    with session_guard(db.session):
        existing_host = find_existing_host(input_host.account, input_host.canonical_facts)
        if existing_host:
            return update_existing_host(existing_host, input_host, staleness_offset, update_system_profile)
        else:
            return create_new_host(input_host, staleness_offset)


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
            existing_host = find_host_by_canonical_facts(account_number, {elevated_cf_name: cf_value})
            if existing_host:
                return existing_host

    return None


def canonical_facts_host_query(account_number, canonical_facts):
    return Host.query.filter(
        (Host.account == account_number)
        & (
            Host.canonical_facts.comparator.contains(canonical_facts)
            | Host.canonical_facts.comparator.contained_by(canonical_facts)
        )
    )


def find_host_by_canonical_facts(account_number, canonical_facts):
    """
    Returns first match for a host containing given canonical facts
    """
    logger.debug("find_host_by_canonical_facts(%s)", canonical_facts)

    host = canonical_facts_host_query(account_number, canonical_facts).first()

    if host:
        logger.debug("Found existing host using canonical_fact match: %s", host)

    return host


@metrics.new_host_commit_processing_time.time()
def create_new_host(input_host, staleness_offset):
    logger.debug("Creating a new host")
    input_host.save()
    db.session.commit()
    metrics.create_host_count.inc()
    logger.debug("Created host:%s", input_host)
    return serialize_host(input_host, staleness_offset), AddHostResults.created


@metrics.update_host_commit_processing_time.time()
def update_existing_host(existing_host, input_host, staleness_offset, update_system_profile):
    logger.debug("Updating an existing host")
    logger.debug(f"existing host = {existing_host}")
    existing_host.update(input_host, update_system_profile)
    db.session.commit()
    metrics.update_host_count.inc()
    logger.debug("Updated host:%s", existing_host)
    return serialize_host(existing_host, staleness_offset), AddHostResults.updated


def stale_timestamp_filter(gte=None, lte=None):
    filter_ = ()
    if gte:
        filter_ += (Host.stale_timestamp >= gte,)
    if lte:
        filter_ += (Host.stale_timestamp <= lte,)
    return and_(*filter_)
