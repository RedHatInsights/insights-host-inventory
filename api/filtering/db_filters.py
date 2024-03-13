from copy import deepcopy
from functools import partial
from typing import List
from uuid import UUID

from dateutil import parser
from sqlalchemy import and_
from sqlalchemy import DateTime
from sqlalchemy import not_
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import JSON

from api.staleness_query import get_staleness_obj
from app.config import HOST_TYPES
from app.culling import staleness_to_conditions
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import OLD_TO_NEW_REPORTER_MAP
from app.serialization import serialize_staleness_to_dict
from app.utils import Tag

__all__ = ("query_filters", "host_id_list_filter", "rbac_permissions_filter")

logger = get_logger(__name__)
DEFAULT_STALENESS_VALUES = ["not_culled"]


def _canonical_fact_filter(canonical_fact: str, value) -> List:
    return [Host.canonical_facts[canonical_fact].astext == value]


def _display_name_filter(display_name: str) -> List:
    return [Host.display_name.comparator.contains(display_name)]


def _tags_filter(string_tags: List[str]) -> List:
    tags = []

    for string_tag in string_tags:
        tags.append(Tag.from_string(string_tag))

    tags_to_find = Tag.create_nested_from_tags(tags)

    return [Host.tags.contains(tags_to_find)]


def _group_names_filter(group_name_list: List) -> List:
    _query_filter = []
    if len(group_name_list) > 0:
        group_filters = [Group.name.in_(group_name_list)]
        if "" in group_name_list:
            group_filters += [HostGroupAssoc.group_id.is_(None)]

        _query_filter += (or_(*group_filters),)

    return _query_filter


def _group_ids_filter(group_id_list: List) -> List:
    _query_filter = []
    if len(group_id_list) > 0:
        group_filters = [HostGroupAssoc.group_id.in_(group_id_list)]
        if None in group_id_list:
            group_filters += [HostGroupAssoc.group_id.is_(None)]

        _query_filter += [or_(*group_filters)]

    return _query_filter


def _stale_timestamp_per_reporter_filter(gt=None, lte=None, host_type=None, reporter=None):
    if reporter.startswith("!"):
        if gt:
            time_filter_ = Host.modified_on > gt
        if lte:
            time_filter_ = Host.modified_on <= lte
        return and_(
            Host.system_profile_facts["host_type"].astext == host_type,
            not_(Host.per_reporter_staleness.has_key(reporter.replace("!", ""))),
            time_filter_,
        )
    else:
        if gt:
            time_filter_ = Host.per_reporter_staleness[reporter]["last_check_in"].astext.cast(DateTime) > gt
        if lte:
            time_filter_ = Host.per_reporter_staleness[reporter]["last_check_in"].astext.cast(DateTime) <= lte
        return and_(
            Host.system_profile_facts["host_type"].astext == host_type,
            Host.per_reporter_staleness.has_key(reporter),
            time_filter_,
        )


def per_reporter_staleness_filter(staleness, reporter):
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj())
    staleness_conditions = tuple()
    for host_type in HOST_TYPES:
        staleness_conditions += tuple(
            staleness_to_conditions(
                staleness_obj, staleness, host_type, partial(_stale_timestamp_per_reporter_filter, reporter=reporter)
            )
        )
    return staleness_conditions


def _staleness_filter(staleness: List[str]) -> List:
    _query_filter = []
    # TODO
    return _query_filter


def _registered_with_filter(registered_with: List[str]) -> List:
    _query_filter = []
    if not registered_with:
        return _query_filter
    reg_with_copy = deepcopy(registered_with)
    if "insights" in registered_with:
        _query_filter.append(Host.canonical_facts["insights_id"] != JSON.NULL)
        reg_with_copy.remove("insights")
    if not reg_with_copy:
        return _query_filter
    # When filtering on old reporter name, include the names of the
    # new reporters associated with the old reporter.
    for old_reporter in OLD_TO_NEW_REPORTER_MAP:
        if old_reporter in reg_with_copy:
            reg_with_copy.extend(OLD_TO_NEW_REPORTER_MAP[old_reporter])
            reg_with_copy = list(set(reg_with_copy))  # Remove duplicates

    # Get the per_report_staleness check_in value for the reporter
    # and build the filter based on it
    for reporter in reg_with_copy:
        prs_item = per_reporter_staleness_filter(DEFAULT_STALENESS_VALUES, reporter)

        for n_items in prs_item:
            _query_filter.append(n_items)
    return [or_(*_query_filter)]


def _system_profile_filter(sp_filter: dict) -> List:
    _query_filter = []
    # TODO
    return _query_filter


def _hostname_or_id_filter(hostname_or_id: str) -> List:
    filter_list = [
        Host.display_name.comparator.contains(hostname_or_id),
        Host.canonical_facts["fqdn"].astext.contains(hostname_or_id),
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


def _modified_on_filter(updated_start: str, updated_end: str) -> List:
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


def host_id_list_filter(host_id_list: List[str]) -> List:
    return [Host.id.in_(host_id_list)]


def rbac_permissions_filter(rbac_filter: dict) -> List:
    _query_filter = []
    if rbac_filter and "groups" in rbac_filter:
        _query_filter = _group_ids_filter(rbac_filter["groups"])

    return _query_filter


def query_filters(
    fqdn: str = None,
    display_name: str = None,
    hostname_or_id: str = None,
    insights_id: str = None,
    provider_id: str = None,
    provider_type: str = None,
    updated_start: str = None,
    updated_end: str = None,
    group_name: str = None,
    group_ids: List[str] = None,
    tags: List[str] = None,
    staleness: List[str] = None,
    registered_with: List[str] = None,
    filter: dict = None,
    rbac_filter: dict = None,
) -> List:
    filters = []
    if fqdn:
        filters += _canonical_fact_filter("fqdn", fqdn)
    elif display_name:
        filters += _display_name_filter(display_name)
    elif hostname_or_id:
        filters += _hostname_or_id_filter(hostname_or_id)
    elif insights_id:
        filters += _canonical_fact_filter("insights_id", insights_id)

    if provider_id:
        filters += _canonical_fact_filter("provider_id", provider_id)
    if provider_type:
        filters += _canonical_fact_filter("provider_type", provider_type)
    if updated_start or updated_end:
        filters += _modified_on_filter(updated_start, updated_end)
    if group_name:
        filters += _group_names_filter(group_name)
    if group_ids:
        filters += _group_ids_filter(group_ids)
    if tags:
        filters += _tags_filter(tags)
    if staleness:
        filters += _staleness_filter(staleness)
    if registered_with:
        filters += _registered_with_filter(registered_with)
    if filter:
        filters += _system_profile_filter(filter)
    if rbac_filter:
        filters += rbac_permissions_filter(rbac_filter)

    return filters
