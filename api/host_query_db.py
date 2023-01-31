from app.auth import get_current_identity
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Host
from datetime import datetime, timezone
from lib.host_repository import update_query_for_owner_id
from sqlalchemy import func

__all__ = ("get_all_hosts", "params_to_order_by")

NULL = None

logger = get_logger(__name__)


def get_all_hosts():
    query = _find_all_hosts()
    query_results = query.all()
    ids_list = [str(host.id) for host in query_results]

    log_get_host_list_succeeded(logger, ids_list)
    return ids_list


def get_host_stats():
    """
    Get the host statistics.

    This hopefully saves the Dashboard three separate API calls, each of which
    reach out to XJoin, and get (a single row of) data which is then thrown
    away because all the Dashboard wants is the count.
    """
    query = _find_all_hosts()
    cfg = inventory_config()
    # Get the main stats we're interested in.  If there was a way to have
    # these as one query rather than three separate queries that'd be great!
    all_hosts = query(func.count(Host.id)).filter(
        {"per_reporter_staleness": {
            "reporter": {"eq": "puptoo"},
        }}
    )
    stale_hosts = query(func.count(Host.id)).filter(
        {"per_reporter_staleness": {
            "reporter": {"eq": "puptoo"},
            "stale_timestamp": {"gt": str((
                datetime.now(timezone.utc) - cfg.culling_stale_warning_offset_delta
            ).isoformat())},
        }}
    )
    warn_hosts = query(func.count(Host.id)).filter(
        {"per_reporter_staleness": {
            "reporter": {"eq": "puptoo"},
            "stale_timestamp": {"gt": str((
                datetime.now(timezone.utc) - cfg.culling_culled_offset_delta
            ).isoformat())},
        }}
    )
    # Maybe there's also a way to take the all_hosts query and clone it before
    # adding the staleness condition?
    return {'total': all_hosts, 'stale': stale_hosts, 'warning': warn_hosts}


def params_to_order_by(order_by=None, order_how=None):
    modified_on_ordering = (Host.modified_on.desc(),)
    ordering = ()

    if order_by == "updated":
        if order_how:
            modified_on_ordering = (_order_how(Host.modified_on, order_how),)
    elif order_by == "display_name":
        if order_how:
            ordering = (_order_how(Host.display_name, order_how),)
        else:
            ordering = (Host.display_name.asc(),)
    elif order_by:
        raise ValueError('Unsupported ordering column, use "updated" or "display_name".')
    elif order_how:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    return ordering + modified_on_ordering + (Host.id.desc(),)


def _order_how(column, order_how):
    if order_how == "ASC":
        return column.asc()
    elif order_how == "DESC":
        return column.desc()
    else:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')


def _find_all_hosts():
    identity = get_current_identity()
    query = Host.query.filter(Host.org_id == identity.org_id)
    return update_query_for_owner_id(identity, query)
