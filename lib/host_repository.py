from __future__ import annotations

from enum import Enum
from uuid import UUID

from flask import current_app
from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_

from api.filtering.db_filters import find_stale_host_in_window
from api.filtering.db_filters import stale_timestamp_filter
from api.filtering.db_filters import staleness_to_conditions
from api.filtering.db_filters import update_query_for_owner_id
from api.staleness_query import get_staleness_obj
from app.auth.identity import Identity
from app.config import ALL_STALENESS_STATES
from app.config import HOST_TYPES
from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness
from lib import metrics
from lib.feature_flags import FLAG_INVENTORY_DEDUPLICATION_ELEVATE_SUBMAN_ID
from lib.feature_flags import get_flag_value

__all__ = (
    "add_host",
    "single_canonical_fact_host_query",
    "multiple_canonical_facts_host_query",
    "create_new_host",
    "find_existing_host",
    "find_host_by_multiple_canonical_facts",
    "find_hosts_by_staleness",
    "find_non_culled_hosts",
    "update_existing_host",
)

AddHostResult = Enum("AddHostResult", ("created", "updated"))

# These are the "elevated" canonical facts that are
# given priority in the host deduplication process.
# NOTE: The order of this tuple is important. The order defines the priority.
ELEVATED_CANONICAL_FACT_FIELDS = ("provider_id", "mac_addresses", "insights_id", "subscription_manager_id")
# These "v2" elevated facts are used when "hbi.deduplication-elevate-subman_id" FF is turned on.
ELEVATED_CANONICAL_FACT_FIELDS_V2 = ("provider_id", "subscription_manager_id", "insights_id")
# This elevated fact is to be used when the USE_SUBMAN_ID env is True
ELEVATED_CANONICAL_FACT_FIELDS_USE_SUBMAN_ID = ("subscription_manager_id",)
COMPOUND_CANONICAL_FACTS_MAP = {"provider_id": "provider_type"}
COMPOUND_CANONICAL_FACTS = tuple(COMPOUND_CANONICAL_FACTS_MAP.values())
IMMUTABLE_CANONICAL_FACTS = ("provider_id",)

NULL = None

logger = get_logger(__name__)


def add_host(
    input_host: Host, identity: Identity, update_system_profile: bool = True, operation_args: dict | None = None
) -> tuple[Host, AddHostResult]:
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - org_id
    """
    if operation_args is None:
        operation_args = {}
    existing_host = find_existing_host(identity, input_host.canonical_facts)
    if existing_host:
        defer_to_reporter = operation_args.get("defer_to_reporter", None)
        if defer_to_reporter is not None:
            logger.debug("host_repository.add_host: defer_to_reporter = %s", defer_to_reporter)
            if not existing_host.reporter_stale(defer_to_reporter):
                logger.debug("host_repository.add_host: setting update_system_profile = False")
                update_system_profile = False

        return update_existing_host(existing_host, input_host, update_system_profile)
    else:
        return create_new_host(input_host)


@metrics.host_dedup_processing_time.time()
def find_existing_host(identity: Identity, canonical_facts: dict) -> Host | None:
    logger.debug("find_existing_host(%s, %s)", identity, canonical_facts)
    existing_host = _find_host_by_elevated_ids(identity, canonical_facts)

    if existing_host or current_app.config["USE_SUBMAN_ID"]:
        return existing_host

    existing_host = find_host_by_multiple_canonical_facts(identity, canonical_facts)

    return existing_host


def find_existing_host_by_id(identity: Identity, host_id: str) -> Host | None:
    query = Host.query.filter((Host.org_id == identity.org_id) & (Host.id == UUID(host_id)))
    query = update_query_for_owner_id(identity, query)
    return find_non_culled_hosts(query, identity).order_by(Host.modified_on.desc()).first()


@metrics.find_host_using_elevated_ids.time()
def _find_host_by_elevated_ids(identity: Identity, canonical_facts: dict) -> Host | None:
    elevated_facts = {}
    elevated_keys = []
    immutable_facts = {}

    elevated_fields = (
        ELEVATED_CANONICAL_FACT_FIELDS_V2
        if get_flag_value(FLAG_INVENTORY_DEDUPLICATION_ELEVATE_SUBMAN_ID, context={"orgId": identity.org_id})
        else ELEVATED_CANONICAL_FACT_FIELDS
    )
    if current_app.config["USE_SUBMAN_ID"]:
        elevated_fields = ELEVATED_CANONICAL_FACT_FIELDS_USE_SUBMAN_ID  # type: ignore
    logger.info(f"Using {elevated_fields} as elevated fields for org {identity.org_id}")

    for key in elevated_fields:
        if key not in canonical_facts.keys():
            continue

        if key in IMMUTABLE_CANONICAL_FACTS:
            immutable_facts[key] = canonical_facts[key]
            if compound_fact := COMPOUND_CANONICAL_FACTS_MAP.get(key):  # noqa: SIM102
                if compound_fact_val := canonical_facts.get(compound_fact):
                    immutable_facts[compound_fact] = compound_fact_val
        else:
            elevated_facts[key] = canonical_facts[key]
            elevated_keys.append(key)

    # First search based on immutable elevated canonical facts.
    if immutable_facts:
        existing_host = (
            multiple_canonical_facts_host_query(identity, immutable_facts, False)
            .order_by(Host.modified_on.desc())
            .first()
        )
        if existing_host:
            return existing_host

    if not elevated_facts:
        return None

    for target_key in elevated_keys:
        #
        # Keep immutable facts in the search, to prevent matching if
        # they are different.
        #
        target_facts = dict(immutable_facts, **{target_key: elevated_facts[target_key]})

        # Ensure both components of compound facts are collected.
        if compound_fact := COMPOUND_CANONICAL_FACTS_MAP.get(target_key):  # noqa: SIM102
            if compound_fact_val := canonical_facts.get(compound_fact):
                target_facts[compound_fact] = compound_fact_val
        existing_host = (
            multiple_canonical_facts_host_query(identity, target_facts, False)
            .order_by(Host.modified_on.desc())
            .first()
        )
        if existing_host:
            return existing_host

    return None


def single_canonical_fact_host_query(identity, canonical_fact, value, restrict_to_owner_id=True):
    query = Host.query.filter(
        (Host.org_id == identity.org_id) & (Host.canonical_facts[canonical_fact].astext == value)
    )
    if restrict_to_owner_id:
        query = update_query_for_owner_id(identity, query)
    return find_non_culled_hosts(query, identity)


# The CanonicalFactsSchema ensures that both components of compound
# canonical facts are provided. This check is included to detect any
# unforeseen issues.
def _check_compound_canonical_facts(canonical_facts):
    for key, value in COMPOUND_CANONICAL_FACTS_MAP.items():
        if key in canonical_facts and value not in canonical_facts:
            raise InventoryException(title="Invalid request", detail=f"Unpaired compound fact: {key} missing {value}")


def multiple_canonical_facts_host_query(identity, canonical_facts, restrict_to_owner_id=True):
    _check_compound_canonical_facts(canonical_facts)

    query = Host.query.filter(
        (Host.org_id == identity.org_id)
        & (contains_no_incorrect_facts_filter(canonical_facts))
        & (matches_at_least_one_canonical_fact_filter(canonical_facts))
    )
    if restrict_to_owner_id:
        query = update_query_for_owner_id(identity, query)
    return find_non_culled_hosts(query, identity)


def find_host_by_multiple_canonical_facts(identity: Identity, canonical_facts: dict) -> Host | None:
    """
    Returns first match for a host containing given canonical facts
    """
    logger.debug("find_host_by_multiple_canonical_facts(%s)", canonical_facts)

    # If no canonical facts are supplied, it can't match anything.
    # Just in case the last canonical fact was removed during the process.
    if not canonical_facts:
        return None

    host = (
        multiple_canonical_facts_host_query(identity, canonical_facts, restrict_to_owner_id=False)
        .order_by(Host.modified_on.desc())
        .first()
    )

    if host:
        logger.debug("Found existing host using canonical_fact match: %s", host)

    return host


def find_hosts_by_staleness(staleness_types, query, identity):
    logger.debug("find_hosts_by_staleness(%s)", staleness_types)
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity.org_id))
    staleness_conditions = [
        or_(False, *staleness_to_conditions(staleness_obj, staleness_types, host_type, stale_timestamp_filter))
        for host_type in HOST_TYPES
    ]

    return query.filter(or_(False, *staleness_conditions))


def find_hosts_by_staleness_job(staleness_types, org_id):
    logger.debug("find_hosts_by_staleness(%s)", staleness_types)
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(org_id))
    staleness_conditions = [
        or_(
            False,
            *staleness_to_conditions(staleness_obj, staleness_types, host_type, stale_timestamp_filter),
        )
        for host_type in HOST_TYPES
    ]

    return or_(False, *staleness_conditions)


def find_stale_hosts(org_id, last_run_secs, job_start_time):
    logger.debug("finding stale hosts with custom staleness")
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(org_id))
    staleness_conditions = [
        or_(
            False,
            *find_stale_host_in_window(staleness_obj, host_type, last_run_secs, job_start_time),
        )
        for host_type in HOST_TYPES
    ]

    return or_(False, *staleness_conditions)


def find_stale_host_sys_default_staleness(last_run_secs, job_start_time):
    logger.debug("finding stale hosts with system default staleness")
    sys_default_staleness = serialize_staleness_to_dict(get_sys_default_staleness())
    staleness_conditions = [
        or_(
            False,
            *find_stale_host_in_window(sys_default_staleness, host_type, last_run_secs, job_start_time),
        )
        for host_type in HOST_TYPES
    ]

    return or_(False, *staleness_conditions)


def find_hosts_sys_default_staleness(staleness_types):
    logger.debug("find hosts with system default staleness")
    sys_default_staleness = serialize_staleness_to_dict(get_sys_default_staleness())
    staleness_conditions = [
        or_(
            False,
            *staleness_to_conditions(sys_default_staleness, staleness_types, host_type, stale_timestamp_filter),
        )
        for host_type in HOST_TYPES
    ]

    return or_(False, *staleness_conditions)


def find_non_culled_hosts(query, identity):
    return find_hosts_by_staleness(ALL_STALENESS_STATES, query, identity)


@metrics.new_host_commit_processing_time.time()
def create_new_host(input_host: Host) -> tuple[Host, AddHostResult]:
    logger.debug("Creating a new host")

    input_host.save()

    metrics.create_host_count.inc()
    logger.debug("Created host (uncommitted):%s", input_host)

    return input_host, AddHostResult.created


@metrics.update_host_commit_processing_time.time()
def update_existing_host(
    existing_host: Host, input_host: Host, update_system_profile: bool
) -> tuple[Host, AddHostResult]:
    logger.debug("Updating an existing host")
    logger.debug(f"existing host = {existing_host}")

    existing_host.update(input_host, update_system_profile)

    metrics.update_host_count.inc()
    logger.debug("Updated host (uncommitted):%s", existing_host)

    return existing_host, AddHostResult.updated


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


def matches_at_least_one_canonical_fact_filter(canonical_facts):
    # Contains at least one correct CF value
    # Correct value = contains key:value
    # -> OR( *correct values )
    filter_ = ()
    for key, value in canonical_facts.items():
        # Don't include the second component of compound canonical facts
        # in the OR logic of the query. It was already included in the
        # AND logic generated by contains_no_incorrect_facts_filter().
        if key in COMPOUND_CANONICAL_FACTS:
            continue
        filter_ += (Host.canonical_facts.contains({key: value}),)

    return or_(*filter_)


def update_system_profile(input_host, identity):
    if not input_host.system_profile_facts:
        raise InventoryException(
            title="Invalid request", detail="Cannot update System Profile, since no System Profile data was provided."
        )

    if input_host.id:
        existing_host = find_existing_host_by_id(identity, input_host.id)
    else:
        existing_host = find_existing_host(identity, input_host.canonical_facts)

    if existing_host:
        logger.debug("Updating system profile on an existing host")
        logger.debug(f"existing host = {existing_host}")

        existing_host.update_system_profile(input_host.system_profile_facts)

        metrics.update_host_count.inc()
        logger.debug("Updated system profile for host (uncommitted):%s", existing_host)

        return existing_host, AddHostResult.updated
    else:
        raise InventoryException(
            title="Invalid request", detail="Could not find an existing host with the provided facts."
        )


def get_host_list_by_id_list_from_db(host_id_list, identity, rbac_filter=None, columns=None):
    filters = (
        Host.org_id == identity.org_id,
        Host.id.in_(host_id_list),
    )
    if rbac_filter and "groups" in rbac_filter:
        rbac_group_filters = (HostGroupAssoc.group_id.in_(rbac_filter["groups"]),)
        if None in rbac_filter["groups"]:
            rbac_group_filters += (
                HostGroupAssoc.group_id.is_(None),
                Group.ungrouped.is_(True),
            )

        filters += (or_(*rbac_group_filters),)

    query = Host.query.join(HostGroupAssoc, isouter=True).join(Group, isouter=True).filter(*filters).group_by(Host.id)
    if columns:
        query = query.with_entities(*columns)
    return find_non_culled_hosts(update_query_for_owner_id(identity, query), identity)
