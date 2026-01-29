from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from functools import partial
from typing import Any
from uuid import UUID

from dateutil import parser
from flask_sqlalchemy.query import Query
from sqlalchemy import DateTime
from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import not_
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import JSONB

from api.filtering.db_custom_filters import build_system_profile_filter
from api.staleness_query import get_staleness_obj
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.config import ALL_STALENESS_STATES
from app.config import DEFAULT_INSIGHTS_ID
from app.culling import Conditions
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models import OLD_TO_NEW_REPORTER_MAP
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import db
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from app.models.constants import WORKLOADS_FIELDS
from app.models.constants import SystemType
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from app.models.system_profile_static import HostStaticSystemProfile
from app.serialization import serialize_staleness_to_dict
from app.staleness_states import HostStalenessStatesDbFilters
from app.utils import Tag
from lib.feature_flags import FLAG_INVENTORY_NEW_STALE_TIMESTAMP_PER_REPORTER_FILTER
from lib.feature_flags import get_flag_value

__all__ = (
    "query_filters",
    "host_id_list_filter",
    "rbac_permissions_filter",
    "stale_timestamp_filter",
    "staleness_to_conditions",
    "update_query_for_owner_id",
    "hosts_field_filter",
)

logger = get_logger(__name__)
DEFAULT_STALENESS_VALUES = ["not_culled"]

# Order-by fields that require a join to HostStaticSystemProfile
ORDER_BY_STATIC_PROFILE_FIELDS = {"operating_system"}


# Cache the column names from system profile tables for performance
_DYNAMIC_PROFILE_FIELDS = None
_STATIC_PROFILE_FIELDS = None


def _get_system_profile_fields():
    """Get the field names from system profile tables by introspecting the models."""
    global _DYNAMIC_PROFILE_FIELDS, _STATIC_PROFILE_FIELDS

    if _DYNAMIC_PROFILE_FIELDS is None:
        # Get column names from HostDynamicSystemProfile (excluding primary keys)
        _DYNAMIC_PROFILE_FIELDS = {
            col.name for col in HostDynamicSystemProfile.__table__.columns if col.name not in ("org_id", "host_id")
        }

    if _STATIC_PROFILE_FIELDS is None:
        # Get column names from HostStaticSystemProfile (excluding primary keys)
        _STATIC_PROFILE_FIELDS = {
            col.name for col in HostStaticSystemProfile.__table__.columns if col.name not in ("org_id", "host_id")
        }

    return _DYNAMIC_PROFILE_FIELDS, _STATIC_PROFILE_FIELDS


def _extract_filter_fields(filter_dict):
    """Extract all field names from a nested filter dictionary."""
    if not filter_dict:
        return set()

    fields = set()
    for key, value in filter_dict.items():
        # Add the top-level key
        fields.add(key)
        # If the value is a dict with nested structure, recurse
        if isinstance(value, dict):
            fields.update(_extract_filter_fields(value))

    return fields


def _needs_system_profile_joins(filter, order_by, system_type):
    """
    Dynamically determine if system profile table joins are needed based on
    which fields are being filtered.

    Returns: (needs_static_join, needs_dynamic_join)
    """
    # system_type always use static profile fields
    if system_type:
        return True, False

    # Ordering by specific fields may require joins even without filters
    requires_static_for_order = order_by in ORDER_BY_STATIC_PROFILE_FIELDS
    if not filter:
        return requires_static_for_order, False

    # Get the system profile field sets
    dynamic_fields, static_fields = _get_system_profile_fields()

    # Extract all fields referenced in the filter
    filter_fields = _extract_filter_fields(filter)

    # Handle workloads fields (temporary)
    # Only needed until we stop supporting the old filter paths
    if filter_fields & WORKLOADS_FIELDS:
        filter_fields.add("workloads")

    # Check if any filter fields match system profile fields
    needs_static = bool(filter_fields & static_fields) or requires_static_for_order
    needs_dynamic = bool(filter_fields & dynamic_fields)

    return needs_static, needs_dynamic


# Static system type filter mappings
SYSTEM_TYPE_FILTERS: dict[str, Any] = {
    SystemType.CONVENTIONAL.value: and_(
        or_(
            HostStaticSystemProfile.bootc_status.is_(None),
            HostStaticSystemProfile.bootc_status["booted"]["image_digest"].astext.is_(None),
            HostStaticSystemProfile.bootc_status["booted"]["image_digest"].astext == "",
        ),
        or_(
            HostStaticSystemProfile.host_type.is_(None),
            HostStaticSystemProfile.host_type == "",
        ),
    ),
    SystemType.BOOTC.value: and_(
        HostStaticSystemProfile.bootc_status.isnot(None),
        HostStaticSystemProfile.bootc_status["booted"]["image_digest"].astext.isnot(None),
        HostStaticSystemProfile.bootc_status["booted"]["image_digest"].astext != "",
    ),
    SystemType.EDGE.value: HostStaticSystemProfile.host_type == SystemType.EDGE.value,
    SystemType.CLUSTER.value: HostStaticSystemProfile.host_type == SystemType.CLUSTER.value,
}


def hosts_field_filter(name: str, value, case_insensitive: bool = False) -> list:
    """Builds a database filter for a Host model attribute."""
    try:
        field = getattr(Host, name)
    except AttributeError as e:
        raise ValidationException(f"Filter key '{name}' is invalid.") from e

    final_value = value.lower() if case_insensitive else value

    expression = func.lower(field) if case_insensitive else field
    return [expression == final_value]


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
            group_filters += [or_(HostGroupAssoc.group_id.is_(None), Group.ungrouped.is_(True))]

        _query_filter += (or_(*group_filters),)

    return _query_filter


def _group_ids_filter(group_id_list: list) -> list:
    _query_filter = []
    if len(group_id_list) > 0:
        group_filters = [HostGroupAssoc.group_id.in_(group_id_list)]
        if None in group_id_list:
            group_filters += [or_(HostGroupAssoc.group_id.is_(None), Group.ungrouped.is_(True))]

        _query_filter += [or_(*group_filters)]

    return _query_filter


def stale_timestamp_filter(gt=None, lte=None):
    filters = []
    if lte is None:
        lte = datetime.now(UTC)
    filters.append(Host.last_check_in <= lte)
    if gt:
        filters.append(Host.last_check_in > gt)
    return and_(*filters)


def _calculate_reporter_timestamps_from_last_check_in(reporter_key: str, staleness_config: dict) -> dict[str, Any]:
    """
    Calculate stale_timestamp, stale_warning_timestamp, and culled_timestamp
    from a reporter's last_check_in using SQLAlchemy expressions.

    This function duplicates the logic from _serialize_per_reporter_staleness
    but returns SQLAlchemy expressions instead of modifying the host object.

    Args:
        reporter_key: The key for the reporter in per_reporter_staleness JSONB
        staleness_config: Dictionary with staleness configuration:
            - conventional_time_to_stale
            - conventional_time_to_stale_warning
            - conventional_time_to_delete

    Returns:
        Dictionary with keys 'stale_timestamp', 'stale_warning_timestamp', 'culled_timestamp'
        containing SQLAlchemy expressions that calculate these values from last_check_in.
    """
    # Get the last_check_in datetime from the JSONB field
    last_check_in = Host.per_reporter_staleness[reporter_key]["last_check_in"].astext.cast(DateTime)

    # Check if host should stay fresh forever (only rhsm-system-profile-bridge reporter)
    # This is equivalent to: per_reporter_staleness has only "rhsm-system-profile-bridge" key
    is_rhsm_only = and_(
        func.jsonb_exists(Host.per_reporter_staleness, "rhsm-system-profile-bridge"),
        Host.per_reporter_staleness.op("-")("rhsm-system-profile-bridge") == cast({}, JSONB),
    )

    # Use FAR_FUTURE_STALE_TIMESTAMP for rhsm-only hosts, otherwise calculate from last_check_in
    far_future = cast(FAR_FUTURE_STALE_TIMESTAMP, DateTime)

    stale_timestamp = case(
        (is_rhsm_only, far_future),
        else_=last_check_in + func.make_interval(seconds=staleness_config["conventional_time_to_stale"]),
    )

    stale_warning_timestamp = case(
        (is_rhsm_only, far_future),
        else_=last_check_in + func.make_interval(seconds=staleness_config["conventional_time_to_stale_warning"]),
    )

    culled_timestamp = case(
        (is_rhsm_only, far_future),
        else_=last_check_in + func.make_interval(seconds=staleness_config["conventional_time_to_delete"]),
    )

    return {
        "stale_timestamp": stale_timestamp,
        "stale_warning_timestamp": stale_warning_timestamp,
        "culled_timestamp": culled_timestamp,
    }


def _stale_timestamp_per_reporter_filter_new(gt=None, lte=None, reporter=None, staleness_config=None):
    """
    New implementation that calculates timestamps from last_check_in on-the-fly.
    This duplicates the logic from _stale_timestamp_per_reporter_filter but uses SQLAlchemy expressions.
    """
    non_negative_reporter = reporter.replace("!", "")
    reporter_list = [non_negative_reporter]
    if non_negative_reporter in OLD_TO_NEW_REPORTER_MAP.keys():
        reporter_list.extend(OLD_TO_NEW_REPORTER_MAP[non_negative_reporter])

    current_time = datetime.now(UTC)

    if reporter.startswith("!"):
        # For negation: include hosts that do NOT have ANY fresh reporter from the reporter_list
        # This means: for ALL reporters in the list, the host either doesn't have them OR they're culled
        time_filter_ = stale_timestamp_filter(gt=gt, lte=lte)

        and_conditions = []  # All conditions must be true (host lacks ALL fresh reporters)

        for rep in reporter_list:
            # Calculate timestamps from last_check_in
            timestamps = _calculate_reporter_timestamps_from_last_check_in(rep, staleness_config)

            # For each reporter, the host must either:
            # 1. Not have this reporter at all, OR
            # 2. Have this reporter but it's culled (calculated culled_timestamp < now)
            rep_condition = or_(
                # Doesn't have this reporter
                not_(Host.per_reporter_staleness.has_key(rep)),
                # Has this reporter but it's culled (calculated culled_timestamp < now)
                and_(
                    Host.per_reporter_staleness.has_key(rep),
                    timestamps["culled_timestamp"] < current_time,
                ),
            )
            and_conditions.append(rep_condition)

        return and_(
            and_(*and_conditions),  # Must satisfy condition for ALL reporters in the list
            time_filter_,
        )
    else:
        # For positive: include hosts that have the reporter AND are not culled
        or_filter = []
        for rep in reporter_list:
            conditions = [Host.per_reporter_staleness.has_key(rep)]

            # Calculate timestamps from last_check_in
            timestamps = _calculate_reporter_timestamps_from_last_check_in(rep, staleness_config)

            # Check if not culled (calculated culled_timestamp >= now)
            conditions.append(timestamps["culled_timestamp"] >= current_time)

            if gt:
                conditions.append(Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) > gt)
            if lte:
                conditions.append(Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) <= lte)
            or_filter.append(and_(*conditions))

        return or_(*or_filter)


def _stale_timestamp_per_reporter_filter(gt=None, lte=None, reporter=None, org_id=None):
    # Check feature flag for new behavior
    if get_flag_value(FLAG_INVENTORY_NEW_STALE_TIMESTAMP_PER_REPORTER_FILTER):
        # Get staleness configuration
        if org_id is None:
            # Fallback to old behavior if org_id is not provided
            logger.warning("Feature flag enabled but org_id not provided, falling back to old behavior")
            # Continue with old behavior below
        else:
            staleness_obj = serialize_staleness_to_dict(get_staleness_obj(org_id))
            return _stale_timestamp_per_reporter_filter_new(gt, lte, reporter, staleness_obj)

    non_negative_reporter = reporter.replace("!", "")
    reporter_list = [non_negative_reporter]
    if non_negative_reporter in OLD_TO_NEW_REPORTER_MAP.keys():
        reporter_list.extend(OLD_TO_NEW_REPORTER_MAP[non_negative_reporter])

    current_time = datetime.now(UTC)

    if reporter.startswith("!"):
        # For negation: include hosts that do NOT have ANY fresh reporter from the reporter_list
        # This means: for ALL reporters in the list, the host either doesn't have them OR they're culled
        time_filter_ = stale_timestamp_filter(gt=gt, lte=lte)

        and_conditions = []  # All conditions must be true (host lacks ALL fresh reporters)

        for rep in reporter_list:
            # For each reporter, the host must either:
            # 1. Not have this reporter at all, OR
            # 2. Have this reporter but it's culled (culled_timestamp < now)
            rep_condition = or_(
                # Doesn't have this reporter
                not_(Host.per_reporter_staleness.has_key(rep)),
                # Has this reporter but it's culled (only if culled_timestamp exists)
                and_(
                    Host.per_reporter_staleness.has_key(rep),
                    Host.per_reporter_staleness[rep].has_key("culled_timestamp"),
                    Host.per_reporter_staleness[rep]["culled_timestamp"].astext.cast(DateTime) < current_time,
                ),
            )
            and_conditions.append(rep_condition)

        return and_(
            and_(*and_conditions),  # Must satisfy condition for ALL reporters in the list
            time_filter_,
        )
    else:
        # For positive: include hosts that have the reporter AND are not culled (if culled_timestamp exists)
        or_filter = []
        for rep in reporter_list:
            # I could start here ####################################3
            conditions = [Host.per_reporter_staleness.has_key(rep)]

            # Only check culled status if culled_timestamp exists
            # If it doesn't exist, include the host (backward compatibility)
            culled_condition = or_(
                # No culled_timestamp field (backward compatibility)
                not_(Host.per_reporter_staleness[rep].has_key("culled_timestamp")),
                # Has culled_timestamp and it's not culled (culled_timestamp >= now)
                Host.per_reporter_staleness[rep]["culled_timestamp"].astext.cast(DateTime) >= current_time,
            )
            conditions.append(culled_condition)

            if gt:
                conditions.append(Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) > gt)
            if lte:
                conditions.append(Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) <= lte)
            or_filter.append(and_(*conditions))

        return or_(*or_filter)


def per_reporter_staleness_filter(staleness, reporter, org_id):
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(org_id))
    conditions = or_(
        *staleness_to_conditions(
            staleness_obj,
            staleness,
            partial(_stale_timestamp_per_reporter_filter, reporter=reporter, org_id=org_id),
        )
    )
    return [conditions]


def _staleness_filter(staleness: list[str]) -> list:
    host_staleness_states_filters = HostStalenessStatesDbFilters()
    if staleness == ["unknown"]:
        # "unknown" filter should be ignored, but shouldn't return culled hosts
        filters = [not_(host_staleness_states_filters.culled())]
    else:
        filters = [getattr(host_staleness_states_filters, state)() for state in staleness if state != "unknown"]
    return [or_(*filters)]


def staleness_to_conditions(
    staleness: dict,
    staleness_states: list[str] | tuple[str, ...],
    timestamp_filter_func: Callable[..., Any],
):
    condition = Conditions(staleness)
    filtered_states = (state for state in staleness_states if state != "unknown")
    return (timestamp_filter_func(*getattr(condition, state)()) for state in filtered_states)


def find_stale_host_in_window(staleness, last_run_secs, job_start_time):
    logger.debug("finding hosts that went stale in the last %s seconds", last_run_secs)
    end_date = job_start_time
    stale_timestamp = end_date - timedelta(seconds=staleness["conventional_time_to_stale"])
    return (
        stale_timestamp_filter(
            stale_timestamp - timedelta(seconds=last_run_secs),
            stale_timestamp,
        ),
    )


def _registered_with_filter(registered_with: list[str], org_id: str) -> list:
    _query_filter: list = []
    if not registered_with:
        return _query_filter
    reg_with_copy = deepcopy(registered_with)
    if "insights" in registered_with:
        _query_filter.append(Host.insights_id != DEFAULT_INSIGHTS_ID)
        reg_with_copy.remove("insights")
    if not reg_with_copy:
        return _query_filter

    # Get the per_report_staleness check_in value for the reporter
    # and build the filter based on it
    for reporter in reg_with_copy:
        prs_item = per_reporter_staleness_filter(DEFAULT_STALENESS_VALUES, reporter, org_id)

        for n_items in prs_item:
            _query_filter.append(n_items)
    return [or_(*_query_filter)]


def _system_profile_filter(filter: dict) -> list:
    query_filters: list = []

    if filter:
        for key in filter:
            if key == "system_profile":
                query_filters += build_system_profile_filter(filter["system_profile"])
            else:
                raise ValidationException("filter key is invalid")

    return query_filters


def _hostname_or_id_filter(hostname_or_id: str) -> tuple:
    wildcard_id = f"%{hostname_or_id.replace('*', '%')}%"
    filter_list = [
        Host.display_name.ilike(wildcard_id),
        Host.fqdn.ilike(wildcard_id),
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

    return [and_(*modified_on_filter)] if modified_on_filter else []


def _last_check_in_filter(last_check_in_start: str | None, last_check_in_end: str | None) -> list:
    last_check_in_filter = []
    last_check_in_start_date = parser.isoparse(last_check_in_start) if last_check_in_start else None
    last_check_in_end_date = parser.isoparse(last_check_in_end) if last_check_in_end else None

    if last_check_in_start_date and last_check_in_end_date and last_check_in_start_date > last_check_in_end_date:
        raise ValueError("last_check_in_start cannot be after last_check_in_end.")

    if last_check_in_start_date and last_check_in_start_date.year > 1970:
        last_check_in_filter += [Host.last_check_in >= last_check_in_start_date]
    if last_check_in_end_date and last_check_in_end_date.year > 1970:
        last_check_in_filter += [Host.last_check_in <= last_check_in_end_date]

    return [and_(*last_check_in_filter)] if last_check_in_filter else []


def host_id_list_filter(host_id_list: list[str]) -> list:
    all_filters = [Host.id.in_(host_id_list)]
    all_filters += _staleness_filter(ALL_STALENESS_STATES)
    return all_filters


def rbac_permissions_filter(rbac_filter: dict) -> list:
    _query_filter = []
    if rbac_filter and "groups" in rbac_filter:
        _query_filter = _group_ids_filter(rbac_filter["groups"])

    return _query_filter


def _is_table_already_joined(query: Query, model) -> bool:
    """
    Check if a model's table is already part of the query's FROM clause.
    Recursively checks all tables and joins in the query.

    Args:
        query: SQLAlchemy Query object
        model: SQLAlchemy model class

    Returns:
        True if the model's table is already joined, False otherwise
    """
    table_name = model.__table__.name

    def check_from_clause(from_clause):
        if hasattr(from_clause, "name") and from_clause.name == table_name:
            return True
        if hasattr(from_clause, "left") and check_from_clause(from_clause.left):
            return True
        return hasattr(from_clause, "right") and check_from_clause(from_clause.right)

    stmt = query.statement if hasattr(query, "statement") else query
    if hasattr(stmt, "get_final_froms"):
        froms = stmt.get_final_froms()
    else:
        return False

    return any(check_from_clause(from_clause) for from_clause in froms)


def update_query_for_owner_id(identity: Identity, query: Query) -> Query:
    # kafka based requests have dummy identity for working around the identity requirement for CRUD operations
    if identity:
        logger.debug("identity auth type: %s", identity.auth_type)
        if identity.identity_type == IdentityType.SYSTEM:
            # Check if HostStaticSystemProfile is already joined to avoid duplicate joins
            if not _is_table_already_joined(query, HostStaticSystemProfile):
                query = query.join(HostStaticSystemProfile, isouter=True)

            return query.filter(HostStaticSystemProfile.owner_id == identity.system["cn"])
    return query


def _system_type_filter(filters: list[str]) -> list:
    invalid = set(filters) - SYSTEM_TYPE_FILTERS.keys()
    if invalid:
        raise ValidationException(f"Invalid system_type: {invalid.pop()}")
    return [or_(*(SYSTEM_TYPE_FILTERS[f] for f in filters))]


def query_filters(
    fqdn: str | None = None,
    display_name: str | None = None,
    hostname_or_id: str | None = None,
    insights_id: str | None = None,
    subscription_manager_id: str | None = None,
    provider_id: str | None = None,
    provider_type: str | None = None,
    updated_start: str | None = None,
    updated_end: str | None = None,
    last_check_in_start: str | None = None,
    last_check_in_end: str | None = None,
    group_name: list[str] | None = None,
    group_ids: list[str] | None = None,
    tags: list[str] | None = None,
    staleness: list[str] | None = None,
    registered_with: list[str] | None = None,
    system_type: list[str] | None = None,
    filter: dict | None = None,
    rbac_filter: dict | None = None,
    order_by: str | None = None,
    identity=None,
    join_static_profile: bool = False,
    join_dynamic_profile: bool = False,
) -> tuple[list, Query]:
    num_ids = sum(bool(id_param) for id_param in [fqdn, display_name, hostname_or_id, insights_id])
    if num_ids > 1:
        raise ValidationException(
            "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        )

    filters = []
    if fqdn:
        filters += hosts_field_filter("fqdn", fqdn, True)
    elif display_name:
        filters += _display_name_filter(display_name)
    elif hostname_or_id:
        filters += _hostname_or_id_filter(hostname_or_id)
    elif insights_id:
        filters += hosts_field_filter("insights_id", insights_id.lower())
    elif subscription_manager_id:
        filters += hosts_field_filter("subscription_manager_id", subscription_manager_id.lower())

    if system_type:
        filters += _system_type_filter(system_type)
    if provider_id:
        filters += hosts_field_filter("provider_id", provider_id, True)
    if provider_type:
        filters += hosts_field_filter("provider_type", provider_type)
    if updated_start or updated_end:
        filters += _modified_on_filter(updated_start, updated_end)
    if last_check_in_start or last_check_in_end:
        filters += _last_check_in_filter(last_check_in_start, last_check_in_end)
    if group_ids:
        filters += _group_ids_filter(group_ids)
    if group_name:
        filters += _group_names_filter(group_name)
    if tags:
        filters += _tags_filter(tags)
    if filter:
        sp_filter = _system_profile_filter(filter)
        filters += sp_filter
    if staleness:
        filters += _staleness_filter(staleness)
    if registered_with:
        filters += _registered_with_filter(registered_with, identity.org_id)
    if rbac_filter:
        filters += rbac_permissions_filter(rbac_filter)

    filters = [and_(Host.org_id == identity.org_id, *filters)]

    # Dynamically determine if we need system profile joins based on what fields are being filtered
    needs_static_join, needs_dynamic_join = _needs_system_profile_joins(filter, order_by, system_type)

    # Allow explicit join requests to override dynamic detection
    needs_static_join = needs_static_join or join_static_profile
    needs_dynamic_join = needs_dynamic_join or join_dynamic_profile

    query_base = db.session.query(Host)

    # Determine base query - start with Host and add group joins if needed
    if group_name or group_ids or rbac_filter or order_by == "group_name":
        query_base = query_base.join(HostGroupAssoc, isouter=True).join(Group, isouter=True)

    # Add system profile joins if needed (dynamic detection or explicit request)
    if needs_static_join:
        query_base = query_base.join(HostStaticSystemProfile, isouter=True)
    if needs_dynamic_join:
        query_base = query_base.join(HostDynamicSystemProfile, isouter=True)

    return filters, query_base
