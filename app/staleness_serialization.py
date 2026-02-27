from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.common import inventory_config
from app.culling import Timestamps
from app.culling import should_host_stay_fresh_forever
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP

if TYPE_CHECKING:
    from app.models.host import Host

# Staleness timestamp dict used when host never goes stale or when reference is missing
FAR_FUTURE_STALENESS_DICT = {
    "stale_timestamp": FAR_FUTURE_STALE_TIMESTAMP,
    "stale_warning_timestamp": FAR_FUTURE_STALE_TIMESTAMP,
    "culled_timestamp": FAR_FUTURE_STALE_TIMESTAMP,
}

__all__ = ("get_staleness_timestamps",)


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def _compute_timestamps_from_date(
    date_to_use: datetime,
    staleness_timestamps: Timestamps,
    staleness: AttrDict,
) -> dict:
    """Compute stale, stale_warning, and culled timestamps from a reference datetime."""
    return {
        "stale_timestamp": staleness_timestamps.stale_timestamp(date_to_use, staleness["conventional_time_to_stale"]),
        "stale_warning_timestamp": staleness_timestamps.stale_warning_timestamp(
            date_to_use, staleness["conventional_time_to_stale_warning"]
        ),
        "culled_timestamp": staleness_timestamps.culled_timestamp(
            date_to_use, staleness["conventional_time_to_delete"]
        ),
    }


# Determine staleness timestamps
def get_staleness_timestamps(host: Host, staleness_timestamps: Timestamps, staleness: AttrDict) -> dict:
    """
    Calculates the single set of staleness timestamps used at host level (top-level
    stale_timestamp, stale_warning_timestamp, culled_timestamp in serialized output).

    Args:
        host: The host object for which to calculate staleness timestamps.
        staleness_timestamps: An object providing methods to compute timestamps.
        staleness: A dictionary containing staleness configuration values.

    Returns:
        dict: A dictionary with keys 'stale_timestamp', 'stale_warning_timestamp', and 'culled_timestamp'.
    """
    if should_host_stay_fresh_forever(host):
        return FAR_FUTURE_STALENESS_DICT.copy()

    return _compute_timestamps_from_date(host.last_check_in, staleness_timestamps, staleness)


def get_reporter_staleness_timestamps(
    host, staleness_timestamps: Timestamps, staleness: AttrDict, reporter: str
) -> dict:
    """
    Calculates staleness timestamps for a specific reporter of a host.
    Returns a dictionary containing the stale, stale warning, and culled timestamps for the reporter.

    Args:
        host: The host object for which to calculate staleness timestamps.
        staleness_timestamps: An object providing methods to compute timestamps.
        staleness: A dictionary containing staleness configuration values.
        reporter: The reporter identifier for which to calculate timestamps.

    Returns:
        dict: A dictionary with keys 'stale_timestamp', 'stale_warning_timestamp', and 'culled_timestamp'.
    """
    if should_host_stay_fresh_forever(host):
        return FAR_FUTURE_STALENESS_DICT.copy()

    if isinstance(host.per_reporter_staleness[reporter], dict):
        last_check_in = host.per_reporter_staleness[reporter]["last_check_in"]
    else:
        last_check_in = host.per_reporter_staleness[reporter]
    date_to_use = datetime.fromisoformat(last_check_in) if isinstance(last_check_in, str) else last_check_in
    return _compute_timestamps_from_date(date_to_use, staleness_timestamps, staleness)


def get_sys_default_staleness(config=None):
    return build_staleness_sys_default("000000", config)


def get_sys_default_staleness_api(identity, config=None):
    org_id = identity.org_id or "00000"
    return build_staleness_sys_default(org_id, config)


def build_staleness_sys_default(org_id, config=None):
    if not config:
        config = inventory_config()

    return AttrDict(
        {
            "id": "system_default",
            "org_id": org_id,
            "conventional_time_to_stale": config.conventional_time_to_stale_seconds,
            "conventional_time_to_stale_warning": config.conventional_time_to_stale_warning_seconds,
            "conventional_time_to_delete": config.conventional_time_to_delete_seconds,
            "immutable_time_to_stale": config.conventional_time_to_stale_seconds,
            "immutable_time_to_stale_warning": config.conventional_time_to_stale_warning_seconds,
            "immutable_time_to_delete": config.conventional_time_to_delete_seconds,
            "created_on": None,
            "modified_on": None,
        }
    )


# This is required because we do not keep a ORM object that is attached to a session
# leaving in the global scope. Before this serialization,
# it was causing sqlalchemy.orm.exc.DetachedInstanceError
def build_serialized_acc_staleness_obj(staleness):
    return AttrDict(
        {
            "id": str(staleness.id),
            "org_id": staleness.org_id,
            "conventional_time_to_stale": staleness.conventional_time_to_stale,
            "conventional_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
            "conventional_time_to_delete": staleness.conventional_time_to_delete,
            "immutable_time_to_stale": staleness.conventional_time_to_stale,
            "immutable_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
            "immutable_time_to_delete": staleness.conventional_time_to_delete,
            "created_on": staleness.created_on,
            "modified_on": staleness.modified_on,
        }
    )
