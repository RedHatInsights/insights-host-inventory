from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from app.common import inventory_config
from app.culling import Timestamps

if TYPE_CHECKING:
    from app.models.host import Host

__all__ = ("get_staleness_timestamps",)


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def get_staleness_timestamps(
    host: Host,
    staleness_timestamps: Timestamps,
    staleness: AttrDict,
    last_check_in: datetime | None = None,
) -> dict:
    """
    Calculates the single set of staleness timestamps used at host level

    Args:
        host: Host row (used for default reference time when ``last_check_in`` is omitted).
        staleness_timestamps: Retained for call-site compatibility; arithmetic uses ``timedelta`` only.
        staleness: Org staleness configuration (conventional_time_to_*).
        last_check_in: Optional reference instant.

    Returns:
        dict with keys ``stale_timestamp``, ``stale_warning_timestamp``, ``culled_timestamp``.

    Raises:
        ValueError: If both ``last_check_in`` and ``host.last_check_in`` are missing (no reference instant).
    """
    _ = staleness_timestamps  # API compatibility; Phase 1 compute-on-read uses offsets only.
    reference = last_check_in if last_check_in is not None else host.last_check_in
    if reference is None:
        raise ValueError("last_check_in is required (pass last_check_in= or set host.last_check_in).")

    stale_seconds = int(staleness["conventional_time_to_stale"])
    warning_seconds = int(staleness["conventional_time_to_stale_warning"])
    delete_seconds = int(staleness["conventional_time_to_delete"])

    return {
        "stale_timestamp": reference + timedelta(seconds=stale_seconds),
        "stale_warning_timestamp": reference + timedelta(seconds=warning_seconds),
        "culled_timestamp": reference + timedelta(seconds=delete_seconds),
    }


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
