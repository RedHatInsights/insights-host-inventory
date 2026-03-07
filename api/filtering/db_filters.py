from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Any
from uuid import UUID

from dateutil import parser
from flask_sqlalchemy.query import Query
from sqlalchemy import DateTime
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import not_
from sqlalchemy import or_
from sqlalchemy.sql.expression import ColumnElement

from api.filtering.db_app_data_filters import build_app_data_filters
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
from app.models.constants import WORKLOADS_FIELDS
from app.models.constants import SystemType
from app.models.host_app_data import get_app_data_models
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from app.models.system_profile_static import HostStaticSystemProfile
from app.serialization import serialize_staleness_to_dict
from app.staleness_states import HostStalenessStatesDbFilters
from app.utils import Tag

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


def _needs_system_profile_joins(filter, order_by):
    """
    Dynamically determine if system profile table joins are needed based on
    which fields are being filtered or sorted.

    Returns: (needs_static_join, needs_dynamic_join)
    """
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


# ALL system types now use Host.host_type directly
# The trigger intelligently derives 'bootc' or 'conventional' from bootc_status
SYSTEM_TYPE_FILTERS: dict[str, Any] = {
    SystemType.CONVENTIONAL.value: Host.host_type == SystemType.CONVENTIONAL.value,
    SystemType.BOOTC.value: Host.host_type == SystemType.BOOTC.value,
    SystemType.EDGE.value: Host.host_type == SystemType.EDGE.value,
    SystemType.CLUSTER.value: Host.host_type == SystemType.CLUSTER.value,
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


def _stale_timestamp_per_reporter_filter(
    reporter: str,
    staleness_config: dict | None = None,
    gt: datetime | None = None,
    lte: datetime | None = None,
) -> ColumnElement:
    """
    Filter hosts by reporter staleness.

    Handles both database formats until RHINENG-21703 is completed:
    - Flat format: {"reporter": "ISO timestamp"}
    - Nested format: {"reporter": {"last_check_in": "...", "culled_timestamp": "...", ...}}

    Uses PostgreSQL's jsonb_typeof() to detect format and apply appropriate logic.

    Args:
        reporter: Reporter name to filter by (required, can start with '!' for negation)
        gt: Filter for timestamps greater than this value
        lte: Filter for timestamps less than or equal to this value
        staleness_config: Staleness configuration dict containing conventional_time_to_delete

    Returns:
        SQLAlchemy filter expression
    """
    non_negative_reporter = reporter.replace("!", "")
    reporter_list = [non_negative_reporter]
    if non_negative_reporter in OLD_TO_NEW_REPORTER_MAP.keys():
        reporter_list.extend(OLD_TO_NEW_REPORTER_MAP[non_negative_reporter])

    current_time = datetime.now(UTC)
    culled_seconds = staleness_config.get("conventional_time_to_delete", 0) if staleness_config else 0
    culled_interval = timedelta(seconds=culled_seconds)

    if reporter.startswith("!"):
        # Negation: exclude hosts with this reporter (or culled)
        time_filter_ = stale_timestamp_filter(gt=gt, lte=lte)
        and_conditions = []

        for rep in reporter_list:
            # For flat format: reporter is culled if computed_culled < now
            flat_format_culled = and_(
                func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "string",
                Host.per_reporter_staleness[rep].astext.cast(DateTime) + culled_interval < current_time,
            )

            # For nested format: reporter is culled if culled_timestamp is in the past
            # If culled_timestamp is missing, calculate it from last_check_in + culled_interval
            # Use COALESCE to use culled_timestamp if present, otherwise calculate from last_check_in
            nested_format_culled = and_(
                func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "object",
                func.coalesce(
                    Host.per_reporter_staleness[rep]["culled_timestamp"].astext.cast(DateTime),
                    Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) + culled_interval,
                )
                < current_time,
            )

            rep_condition = or_(
                not_(Host.per_reporter_staleness.has_key(rep)),  # No reporter
                flat_format_culled,  # Flat format and culled
                nested_format_culled,  # Nested format and culled
            )
            and_conditions.append(rep_condition)

        return and_(and_(*and_conditions), time_filter_)
    else:
        # Positive: include hosts with this reporter (not culled)
        or_filter = []
        for rep in reporter_list:
            conditions = [Host.per_reporter_staleness.has_key(rep)]

            # For flat format: not culled if computed_culled >= now
            flat_format_not_culled = and_(
                func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "string",
                Host.per_reporter_staleness[rep].astext.cast(DateTime) + culled_interval >= current_time,
            )

            # For nested format: not culled if culled_timestamp >= now
            # If culled_timestamp is missing, calculate it from last_check_in + culled_interval
            # Use COALESCE to use culled_timestamp if present, otherwise calculate from last_check_in
            nested_format_not_culled = and_(
                func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "object",
                func.coalesce(
                    Host.per_reporter_staleness[rep]["culled_timestamp"].astext.cast(DateTime),
                    Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) + culled_interval,
                )
                >= current_time,
            )

            # Either format is acceptable as long as not culled
            conditions.append(or_(flat_format_not_culled, nested_format_not_culled))

            # Time range filters - handle both formats
            if gt:
                flat_gt = and_(
                    func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "string",
                    Host.per_reporter_staleness[rep].astext.cast(DateTime) > gt,
                )
                nested_gt = and_(
                    func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "object",
                    Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) > gt,
                )
                conditions.append(or_(flat_gt, nested_gt))

            if lte:
                flat_lte = and_(
                    func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "string",
                    Host.per_reporter_staleness[rep].astext.cast(DateTime) <= lte,
                )
                nested_lte = and_(
                    func.jsonb_typeof(Host.per_reporter_staleness[rep]) == "object",
                    Host.per_reporter_staleness[rep]["last_check_in"].astext.cast(DateTime) <= lte,
                )
                conditions.append(or_(flat_lte, nested_lte))

            or_filter.append(and_(*conditions))

        return or_(*or_filter)


def per_reporter_staleness_filter(staleness, reporter, org_id):
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj(org_id))
    conditions = or_(
        *staleness_to_conditions(
            staleness_obj,
            staleness,
            lambda gt, lte: _stale_timestamp_per_reporter_filter(
                reporter=reporter, staleness_config=staleness_obj, gt=gt, lte=lte
            ),
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


def _registered_with_filter(registered_with: list[str], org_id: str, staleness: list[str] | None = None) -> list:
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
    # If staleness is provided, use it to filter by per-reporter staleness state
    # Otherwise, default to "not_culled" to only exclude culled reporters
    staleness_states = staleness if staleness is not None else DEFAULT_STALENESS_VALUES
    for reporter in reg_with_copy:
        prs_item = per_reporter_staleness_filter(staleness_states, reporter, org_id)

        for n_items in prs_item:
            _query_filter.append(n_items)
    return [or_(*_query_filter)]


def _build_filter(filter: dict) -> tuple[list, set]:
    query_filters: list = []
    app_models_to_join: set = set()

    if filter:
        app_data_models = get_app_data_models()
        app_filter_dict = {}
        for key in filter:
            if key == "system_profile":
                query_filters += build_system_profile_filter(filter["system_profile"])
            elif key in app_data_models:
                app_filter_dict[key] = filter[key]
            else:
                raise ValidationException("filter key is invalid")
        if app_filter_dict:
            app_filters, app_models_to_join = build_app_data_filters(app_filter_dict)
            query_filters += app_filters

    return query_filters, app_models_to_join


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

    app_data_models_to_join = set[Any]()

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
        filter_exprs, app_data_models_to_join = _build_filter(filter)
        filters += filter_exprs
    if staleness:
        filters += _staleness_filter(staleness)
    if registered_with:
        filters += _registered_with_filter(registered_with, identity.org_id)
    if rbac_filter:
        filters += rbac_permissions_filter(rbac_filter)

    filters = [and_(Host.org_id == identity.org_id, *filters)]

    # Dynamically determine if we need system profile joins based on filtering and ordering
    needs_static_join, needs_dynamic_join = _needs_system_profile_joins(filter, order_by)

    # Allow explicit join requests to override dynamic detection
    needs_static_join = needs_static_join or join_static_profile
    needs_dynamic_join = needs_dynamic_join or join_dynamic_profile

    query_base = db.session.query(Host)

    # Determine base query - start with Host and add group joins if needed
    if group_name or group_ids or rbac_filter or order_by == "group_name":
        query_base = query_base.outerjoin(HostGroupAssoc).outerjoin(Group)

    # Add system profile joins if needed (dynamic detection or explicit request)
    if needs_static_join:
        query_base = query_base.outerjoin(HostStaticSystemProfile)
    if needs_dynamic_join:
        query_base = query_base.outerjoin(HostDynamicSystemProfile)

    # Add app data joins for filtering
    for model_class in app_data_models_to_join:
        query_base = query_base.outerjoin(model_class)

    return filters, query_base
