from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any
from uuid import UUID

from flask import current_app
from flask_sqlalchemy.query import Query
from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_
from sqlalchemy.sql.elements import BinaryExpression
from sqlalchemy.sql.elements import BooleanClauseList

from api.filtering.db_filters import find_stale_host_in_window
from api.filtering.db_filters import stale_timestamp_filter
from api.filtering.db_filters import staleness_to_conditions
from api.filtering.db_filters import update_query_for_owner_id
from api.staleness_query import get_staleness_obj
from app.auth.identity import Identity
from app.common import inventory_config
from app.config import ALL_STALENESS_STATES
from app.config import COMPOUND_ID_FACTS
from app.config import COMPOUND_ID_FACTS_MAP
from app.config import HOST_TYPES
from app.config import ID_FACTS
from app.config import ID_FACTS_USE_SUBMAN_ID
from app.config import IMMUTABLE_ID_FACTS
from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import LimitedHost
from app.models import db
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness
from lib import metrics

__all__ = (
    "AddHostResult",
    "extract_immutable_and_id_facts",
    "add_host",
    "multiple_canonical_facts_host_query",
    "create_new_host",
    "find_existing_host",
    "find_hosts_by_staleness",
    "find_non_culled_hosts",
    "update_existing_host",
)

AddHostResult = Enum("AddHostResult", ("created", "updated"))

logger = get_logger(__name__)


def add_host(
    input_host: Host,
    identity: Identity,
    update_system_profile: bool = True,
    operation_args: dict | None = None,
    existing_hosts: list[Host] | None = None,
) -> tuple[Host, AddHostResult]:
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - org_id

     The only supported argument in the operation_args for now is "defer_to_reporter".
     It is documented here:
     https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
    """
    if operation_args is None:
        operation_args = {}

    matched_host = None
    if existing_hosts:
        # First, try to match the host in memory - from the provided list of existing hosts
        matched_host = find_existing_host(identity, input_host.canonical_facts, existing_hosts)
    if matched_host is None:
        # If the list of existing hosts was not provided, or the match was not found, try querying DB
        matched_host = find_existing_host(identity, input_host.canonical_facts)

    if matched_host:
        defer_to_reporter = operation_args.get("defer_to_reporter")
        if defer_to_reporter is not None:
            logger.debug("host_repository.add_host: defer_to_reporter = %s", defer_to_reporter)
            if not matched_host.reporter_stale(defer_to_reporter):
                logger.debug("host_repository.add_host: setting update_system_profile = False")
                update_system_profile = False

        return update_existing_host(matched_host, input_host, update_system_profile)
    else:
        return create_new_host(input_host)


def extract_immutable_and_id_facts(canonical_facts: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Returns two dictionaries:
    - immutable_facts: All immutable facts present in the canonical facts, together with their compound facts
    - id_facts: All id facts present in the canonical facts, except for the immutable facts
    """
    id_fields = ID_FACTS_USE_SUBMAN_ID if current_app.config["USE_SUBMAN_ID"] else ID_FACTS
    logger.debug(f"Using {id_fields} for deduplication")

    immutable_facts = {}
    id_facts = {}

    # Iterate through the ID fields in the priority order
    for key in id_fields:
        if key not in canonical_facts.keys():
            continue

        if key in IMMUTABLE_ID_FACTS:
            immutable_facts[key] = canonical_facts[key]
            # Add compound facts (for example, add provider_type if provider_id is present)
            if compound_fact := COMPOUND_ID_FACTS_MAP.get(key):  # noqa: SIM102
                if compound_fact_value := canonical_facts.get(compound_fact):
                    immutable_facts[compound_fact] = compound_fact_value
        else:
            id_facts[key] = canonical_facts[key]

    return immutable_facts, id_facts


@metrics.host_dedup_processing_time.time()
def find_existing_host(
    identity: Identity, canonical_facts: dict[str, Any], from_hosts: list[Host] | None = None
) -> Host | None:
    logger.debug(f"find_existing_host({identity}, {canonical_facts}, {from_hosts})")
    immutable_facts, id_facts = extract_immutable_and_id_facts(canonical_facts)

    # First search based on immutable id facts.
    if immutable_facts:  # noqa: SIM102
        if existing_host := _find_host_by_multiple_facts_in_db_or_in_memory(identity, immutable_facts, from_hosts):
            return existing_host

    if not id_facts:
        return None

    # Now search based on other ID facts
    # Dicts have been ordered since Python 3.7, so the priority ordering will be respected
    for target_key, target_value in id_facts.items():
        # Keep immutable facts in the search to prevent matching if they are different.
        target_facts = dict(immutable_facts, **{target_key: target_value})

        # Ensure both components of compound facts are collected.
        if compound_fact := COMPOUND_ID_FACTS_MAP.get(target_key):  # noqa: SIM102
            if compound_fact_value := canonical_facts.get(compound_fact):
                target_facts[compound_fact] = compound_fact_value

        if existing_host := _find_host_by_multiple_facts_in_db_or_in_memory(identity, target_facts, from_hosts):
            return existing_host

    return None


def find_existing_host_by_id(identity: Identity, host_id: str) -> Host | None:
    query = Host.query.filter((Host.org_id == identity.org_id) & (Host.id == UUID(host_id)))
    query = update_query_for_owner_id(identity, query)
    return find_non_culled_hosts(query, identity.org_id).order_by(Host.modified_on.desc()).first()


def _find_host_by_multiple_facts_in_db_or_in_memory(
    identity: Identity, canonical_facts: dict[str, str], from_hosts: list[Host] | None = None
) -> Host | None:
    if from_hosts:
        with metrics.find_host_by_facts_in_memory.time():
            existing_hosts = list(
                filter(multiple_canonical_facts_host_query_in_memory(identity, canonical_facts), from_hosts)
            )
        return existing_hosts[0] if existing_hosts else None

    with metrics.find_host_by_facts_in_db.time():
        return (
            multiple_canonical_facts_host_query(identity, canonical_facts, restrict_to_owner_id=False)
            .order_by(Host.modified_on.desc())
            .first()
        )


# The CanonicalFactsSchema ensures that both components of compound
# canonical facts are provided. This check is included to detect any
# unforeseen issues.
def _check_compound_id_facts(canonical_facts: dict[str, Any]) -> None:
    for key, value in COMPOUND_ID_FACTS_MAP.items():
        if key in canonical_facts and value not in canonical_facts:
            raise InventoryException(title="Invalid request", detail=f"Unpaired compound fact: {key} missing {value}")


def multiple_canonical_facts_host_query(
    identity: Identity, canonical_facts: dict[str, Any], restrict_to_owner_id: bool = True
) -> Query:
    _check_compound_id_facts(canonical_facts)

    query = Host.query.filter(
        (Host.org_id == identity.org_id)
        & (contains_no_incorrect_facts_filter(canonical_facts))
        & (matches_at_least_one_canonical_fact_filter(canonical_facts))
    )
    if restrict_to_owner_id:
        query = update_query_for_owner_id(identity, query)
    return find_non_culled_hosts(query, identity.org_id)


def multiple_canonical_facts_host_query_in_memory(
    identity: Identity, canonical_facts: dict[str, Any]
) -> Callable[[Host], bool]:
    def _query(host: Host) -> bool:
        return (
            host.org_id == identity.org_id
            and contains_no_incorrect_facts_filter_in_memory(host, canonical_facts)
            and matches_at_least_one_canonical_fact_filter_in_memory(host, canonical_facts)
        )

    return _query


def find_hosts_by_staleness(staleness_types: list[str], query: Query, org_id: str) -> Query:
    logger.debug("find_hosts_by_staleness(%s)", staleness_types)
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(org_id))
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


def find_non_culled_hosts(query: Query, org_id: str) -> Query:
    return find_hosts_by_staleness(ALL_STALENESS_STATES, query, org_id)


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


def contains_no_incorrect_facts_filter(canonical_facts: dict[str, Any]) -> BinaryExpression:
    # Does not contain any incorrect CF values
    # Incorrect value = AND( key exists, NOT( contains key:value ) )
    # -> NOT( OR( *Incorrect values ) )
    filter_: tuple = ()
    for key, value in canonical_facts.items():
        filter_ += (and_(Host.canonical_facts.has_key(key), not_(Host.canonical_facts.contains({key: value}))),)

    return not_(or_(*filter_))


def contains_no_incorrect_facts_filter_in_memory(host: Host, canonical_facts: dict[str, Any]) -> bool:
    def _per_fact_query(host: Host, key: str, value: Any) -> bool:
        # Either the key is not present in the host, or the fact matches
        return key not in host.canonical_facts or host.canonical_facts[key] == value

    return all(_per_fact_query(host, key, value) for key, value in canonical_facts.items())


def matches_at_least_one_canonical_fact_filter(canonical_facts: dict[str, Any]) -> BooleanClauseList:
    # Contains at least one correct CF value
    # Correct value = contains key:value
    # -> OR( *correct values )
    filter_: tuple = ()
    for key, value in canonical_facts.items():
        # Don't include the second component of compound canonical facts
        # in the OR logic of the query. It was already included in the
        # AND logic generated by contains_no_incorrect_facts_filter().
        if key in COMPOUND_ID_FACTS:
            continue
        filter_ += (Host.canonical_facts.contains({key: value}),)

    return or_(*filter_)


def matches_at_least_one_canonical_fact_filter_in_memory(host: Host, canonical_facts: dict[str, Any]) -> bool:
    return any(host.canonical_facts.get(key) == value for key, value in canonical_facts.items())


def update_system_profile(input_host: Host | LimitedHost, identity: Identity):
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

    if inventory_config().hbi_db_refactoring_use_old_table:
        # Old code: use single column GROUP BY
        query = (
            Host.query.join(HostGroupAssoc, isouter=True).join(Group, isouter=True).filter(*filters).group_by(Host.id)
        )
    else:
        # New code: use composite GROUP BY
        query = (
            Host.query.join(HostGroupAssoc, isouter=True)
            .join(Group, isouter=True)
            .filter(*filters)
            .group_by(Host.id, Host.org_id)
        )
    if columns:
        query = query.with_entities(*columns)
    return find_non_culled_hosts(update_query_for_owner_id(identity, query), identity.org_id)


def get_non_culled_hosts_count_in_group(group: Group, org_id: str) -> int:
    if inventory_config().hbi_db_refactoring_use_old_table:
        # Old code: use single column GROUP BY
        query = (
            db.session.query(Host).join(HostGroupAssoc).filter(HostGroupAssoc.group_id == group.id).group_by(Host.id)
        )
    else:
        # New code: use composite GROUP BY
        query = (
            db.session.query(Host)
            .join(HostGroupAssoc)
            .filter(HostGroupAssoc.group_id == group.id, HostGroupAssoc.org_id == org_id)
            .group_by(Host.id, Host.org_id)
        )

    return find_non_culled_hosts(query, org_id).count()
