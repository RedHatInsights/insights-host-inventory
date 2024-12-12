from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from functools import partial
from uuid import UUID

from dateutil import parser
from flask_sqlalchemy.query import Query
from sqlalchemy import DateTime
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import not_
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import JSON

from api.filtering.db_custom_filters import build_system_profile_filter
from api.filtering.db_custom_filters import get_host_types_from_filter
from api.staleness_query import get_staleness_obj
from app.auth.identity import IdentityType
from app.config import ALL_STALENESS_STATES
from app.config import HOST_TYPES
from app.culling import Conditions
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models import OLD_TO_NEW_REPORTER_MAP
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import db
from app.serialization import serialize_staleness_to_dict
from app.utils import Tag

__all__ = (
    "canonical_fact_filter",
    "query_filters",
    "host_id_list_filter",
    "rbac_permissions_filter",
    "stale_timestamp_filter",
    "staleness_to_conditions",
    "update_query_for_owner_id",
)

logger = get_logger(__name__)
DEFAULT_STALENESS_VALUES = ["not_culled"]


def canonical_fact_filter(canonical_fact: str, value, case_insensitive: bool = False) -> list:
    if case_insensitive:
        return [func.lower(Host.canonical_facts[canonical_fact].astext) == value.lower()]
    return [Host.canonical_facts[canonical_fact].astext == value]


def _display_name_filter(display_name: str) -> list:
    return [Host.display_name.ilike(f"%{display_name.replace('*', '%')}%")]


def _tags_filter(string_tags: list[str]) -> list:
    tags = []

    for string_tag in string_tags:
        tags.append(Tag.create_nested_from_tags([Tag.from_string(string_tag)]))

    return [or_(Host.tags.contains(tag) for tag in tags)]


def _group_names_filter(group_name_list: list) -> list:
    _query_filter: list = []
    group_name_list_lower = [group_name.lower() for group_name in group_name_list]
    if len(group_name_list) > 0:
        group_filters = [func.lower(Group.name).in_(group_name_list_lower)]
        if "" in group_name_list:
            group_filters += [HostGroupAssoc.group_id.is_(None)]

        _query_filter += (or_(*group_filters),)

    return _query_filter


def _group_ids_filter(group_id_list: list) -> list:
    _query_filter = []
    if len(group_id_list) > 0:
        group_filters = [HostGroupAssoc.group_id.in_(group_id_list)]
        if None in group_id_list:
            group_filters += [HostGroupAssoc.group_id.is_(None)]

        _query_filter += [or_(*group_filters)]

    return _query_filter


def stale_timestamp_filter(gt=None, lte=None):
    filters = []
    if gt:
        filters.append(Host.modified_on > gt)
    if lte:
        filters.append(Host.modified_on <= lte)

    return and_(*filters)


def _host_type_filter(host_type: str | None):
    return Host.system_profile_facts["host_type"].as_string() == host_type


def _stale_timestamp_per_reporter_filter(gt=None, lte=None, reporter=None):
    non_negative_reporter = reporter.replace("!", "")
    reporter_list = [non_negative_reporter]
    if non_negative_reporter in OLD_TO_NEW_REPORTER_MAP.keys():
        reporter_list.extend(OLD_TO_NEW_REPORTER_MAP[non_negative_reporter])

    if reporter.startswith("!"):
        time_filter_ = stale_timestamp_filter(gt=gt, lte=lte)
        return and_(
            and_(
                not_(Host.per_reporter_staleness.has_key(rep)),
                time_filter_,
            )
            for rep in reporter_list
        )
    else:
        or_filter = []
        for rep in reporter_list:
            if gt:
                time_filter_ = Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) > gt
            if lte:
                time_filter_ = Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) <= lte
            or_filter.append(
                and_(
                    Host.per_reporter_staleness.has_key(rep),
                    time_filter_,
                )
            )

        return or_(*or_filter)


def per_reporter_staleness_filter(staleness, reporter, host_type_filter):
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj())
    staleness_conditions = []
    for host_type in host_type_filter:
        conditions = or_(
            *staleness_to_conditions(
                staleness_obj,
                staleness,
                host_type,
                partial(_stale_timestamp_per_reporter_filter, reporter=reporter),
                True,
            )
        )
        if len(host_type_filter) > 1:
            staleness_conditions.append(
                and_(
                    _host_type_filter(host_type),
                    conditions,
                )
            )
        else:
            staleness_conditions.append(conditions)

    return staleness_conditions


def _staleness_filter(
    staleness: list[str] | tuple[str, ...], host_type_filter: set[str | None], identity=None
) -> list:
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity))
    staleness_conditions = []
    for host_type in host_type_filter:
        conditions = or_(*staleness_to_conditions(staleness_obj, staleness, host_type, stale_timestamp_filter, True))
        if len(host_type_filter) > 1:
            staleness_conditions.append(
                and_(
                    _host_type_filter(host_type),
                    conditions,
                )
            )
        else:
            staleness_conditions.append(conditions)

    return [or_(*staleness_conditions)]


def staleness_to_conditions(
    staleness, staleness_states, host_type, timestamp_filter_func, omit_host_type_filter: bool = False
):
    def _timestamp_and_host_type_filter(condition, state):
        filter_ = timestamp_filter_func(*getattr(condition, state)())
        if omit_host_type_filter:
            return filter_
        else:
            return and_(filter_, _host_type_filter(host_type))

    condition = Conditions(staleness, host_type)
    filtered_states = (state for state in staleness_states if state != "unknown")
    return (_timestamp_and_host_type_filter(condition, state) for state in filtered_states)


def find_stale_host_in_window(staleness, host_type, last_run_secs, job_start_time):
    logger.debug("finding hosts that went stale in the last %s seconds", last_run_secs)
    end_date = job_start_time
    prefix = "immutable" if host_type == "edge" else "conventional"
    stale_timestamp = end_date - timedelta(seconds=staleness[f"{prefix}_time_to_stale"])
    return (
        stale_timestamp_filter(
            stale_timestamp - timedelta(seconds=last_run_secs),
            stale_timestamp,
        ),
    )


def _registered_with_filter(registered_with: list[str], host_type_filter: set[str | None]) -> list:
    _query_filter: list = []
    if not registered_with:
        return _query_filter
    reg_with_copy = deepcopy(registered_with)
    if "insights" in registered_with:
        _query_filter.append(Host.canonical_facts["insights_id"] != JSON.NULL)
        reg_with_copy.remove("insights")
    if not reg_with_copy:
        return _query_filter

    # Get the per_report_staleness check_in value for the reporter
    # and build the filter based on it
    for reporter in reg_with_copy:
        prs_item = per_reporter_staleness_filter(DEFAULT_STALENESS_VALUES, reporter, host_type_filter)

        for n_items in prs_item:
            _query_filter.append(n_items)
    return [or_(*_query_filter)]


def _system_profile_filter(filter: dict) -> tuple[list, set[str | None]]:
    query_filters: list = []
    host_types = set(HOST_TYPES.copy())

    if filter:
        for key in filter:
            if key == "system_profile":
                # Get the host_types we're filtering on, if any
                host_types = get_host_types_from_filter(filter["system_profile"].get("host_type"))

                query_filters += build_system_profile_filter(filter["system_profile"])
            else:
                raise ValidationException("filter key is invalid")

    return query_filters, host_types


def _hostname_or_id_filter(hostname_or_id: str) -> tuple:
    wildcard_id = f"%{hostname_or_id.replace('*', '%')}%"
    filter_list = [
        Host.display_name.ilike(wildcard_id),
        Host.canonical_facts["fqdn"].astext.ilike(wildcard_id),
    ]

    try:
        UUID(hostname_or_id)
        host_id = hostname_or_id
        filter_list.append(Host.id == host_id)
        logger.debug("Adding id (uuid) to the filter list")
    except Exception:
        # Do not filter using the id
        logger.debug("The hostname (%s) could not be converted into a UUID", hostname_or_id, exc_info=True)

    return (or_(*filter_list),)


def _modified_on_filter(updated_start: str | None, updated_end: str | None) -> list:
    modified_on_filter = []
    updated_start_date = parser.isoparse(updated_start) if updated_start else None
    updated_end_date = parser.isoparse(updated_end) if updated_end else None

    if updated_start_date and updated_end_date and updated_start_date > updated_end_date:
        raise ValueError("updated_start cannot be after updated_end.")

    if updated_start_date and updated_start_date.year > 1970:
        modified_on_filter += [Host.modified_on >= updated_start_date]
    if updated_end_date and updated_end_date.year > 1970:
        modified_on_filter += [Host.modified_on <= updated_end_date]

    return [and_(*modified_on_filter)]


def host_id_list_filter(host_id_list: list[str]) -> list:
    all_filters = [Host.id.in_(host_id_list)]
    all_filters += _staleness_filter(ALL_STALENESS_STATES, set(HOST_TYPES.copy()))
    return all_filters


def rbac_permissions_filter(rbac_filter: dict) -> list:
    _query_filter = []
    if rbac_filter and "groups" in rbac_filter:
        _query_filter = _group_ids_filter(rbac_filter["groups"])

    return _query_filter


def update_query_for_owner_id(identity, query):
    # kafka based requests have dummy identity for working around the identity requirement for CRUD operations
    logger.debug("identity auth type: %s", identity.auth_type)
    if identity and identity.identity_type == IdentityType.SYSTEM:
        return query.filter(and_(Host.system_profile_facts["owner_id"].as_string() == identity.system["cn"]))
    else:
        return query


def query_filters(
    fqdn: str | None = None,
    display_name: str | None = None,
    hostname_or_id: str | None = None,
    insights_id: str | None = None,
    provider_id: str | None = None,
    provider_type: str | None = None,
    updated_start: str | None = None,
    updated_end: str | None = None,
    group_name: list[str] | None = None,
    group_ids: list[str] | None = None,
    tags: list[str] | None = None,
    staleness: list[str] | tuple[str, ...] | None = None,
    registered_with: list[str] | None = None,
    filter: dict | None = None,
    rbac_filter: dict | None = None,
    order_by: str | None = None,
    identity=None,
) -> tuple[list, Query]:
    num_ids = 0
    host_type_filter = set(HOST_TYPES)
    for id_param in [fqdn, display_name, hostname_or_id, insights_id]:
        if id_param:
            num_ids += 1

    if num_ids > 1:
        raise ValidationException(
            "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        )

    filters = []
    if fqdn:
        filters += canonical_fact_filter("fqdn", fqdn, case_insensitive=True)
    elif display_name:
        filters += _display_name_filter(display_name)
    elif hostname_or_id:
        filters += _hostname_or_id_filter(hostname_or_id)
    elif insights_id:
        filters += canonical_fact_filter("insights_id", insights_id.lower())

    if provider_id:
        filters += canonical_fact_filter("provider_id", provider_id, case_insensitive=True)
    if provider_type:
        filters += canonical_fact_filter("provider_type", provider_type)
    if updated_start or updated_end:
        filters += _modified_on_filter(updated_start, updated_end)
    if group_ids:
        filters += _group_ids_filter(group_ids)
    if group_name:
        filters += _group_names_filter(group_name)
    if tags:
        filters += _tags_filter(tags)
    if filter:
        sp_filter, host_type_filter = _system_profile_filter(filter)
        filters += sp_filter
    if staleness:
        filters += _staleness_filter(staleness, host_type_filter, identity)
    if registered_with:
        filters += _registered_with_filter(registered_with, host_type_filter)
    if rbac_filter:
        filters += rbac_permissions_filter(rbac_filter)

    # Determine query_base
    if group_name or order_by == "group_name":
        query_base = db.session.query(Host).join(HostGroupAssoc, isouter=True).join(Group, isouter=True)
    elif group_ids or rbac_filter:
        query_base = db.session.query(Host).join(HostGroupAssoc, isouter=True)
    else:
        query_base = db.session.query(Host)

    return filters, query_base
