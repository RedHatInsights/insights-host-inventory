from collections import namedtuple
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.host import Host

__all__ = (
    "Conditions",
    "Timestamps",
    "days_to_seconds",
    "seconds_to_days",
    "CONVENTIONAL_TIME_TO_STALE_SECONDS",
    "CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS",
    "CONVENTIONAL_TIME_TO_DELETE_SECONDS",
)

# Time period of inactivity before the system becomes stale. (Hosts are
# expected to check in nightly, but to accommodate for potential delays like a
# randomized check-in window and overnight Kafka lag, the extra 5 hours beyond
# the standard 24 hours provide a buffer).
# Default: 104400 seconds (29 hours)
CONVENTIONAL_TIME_TO_STALE_SECONDS = 104400

# Time period of inactivity before the system is in "stale_warning" state.
# Default: 604800 seconds (7 days).
CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS = 604800

# Time period of inactivity before the system is deleted from the database.
# Default: 2592000 seconds (30 days).
CONVENTIONAL_TIME_TO_DELETE_SECONDS = 2592000


class _Config(namedtuple("_Config", ("stale_warning_offset_delta", "culled_offset_delta"))):
    @classmethod
    def from_config(cls, config):
        return cls(config.culling_stale_warning_offset_delta, config.culling_culled_offset_delta)


class _WithConfig:
    def __init__(self, config):
        self.config = config

    @classmethod
    def from_config(cls, config):
        config = _Config.from_config(config)
        return cls(config)


class Timestamps(_WithConfig):
    @staticmethod
    def _add_time(timestamp, delta):
        return timestamp + delta

    def stale_timestamp(self, stale_timestamp, stale_seconds):
        return self._add_time(stale_timestamp, timedelta(seconds=stale_seconds))

    def stale_warning_timestamp(self, stale_timestamp, stale_warning_seconds):
        return self._add_time(stale_timestamp, timedelta(seconds=stale_warning_seconds))

    def culled_timestamp(self, stale_timestamp, culled_seconds):
        return self._add_time(stale_timestamp, timedelta(seconds=culled_seconds))


class Conditions:
    def __init__(self, staleness):
        self.now = datetime.now(UTC)
        self.staleness_setting = {
            "stale": staleness["conventional_time_to_stale"],
            "warning": staleness["conventional_time_to_stale_warning"],
            "culled": staleness["conventional_time_to_delete"],
        }

    def fresh(self):
        return self._stale_timestamp(), None

    def stale(self):
        return self._stale_warning_timestamp(), self._stale_timestamp()

    def stale_warning(self):
        return self._culled_timestamp(), self._stale_warning_timestamp()

    def culled(self):
        return None, self._culled_timestamp()

    def not_culled(self):
        return self._culled_timestamp(), None

    def _stale_timestamp(self):
        offset = timedelta(seconds=self.staleness_setting["stale"])
        return self.now - offset

    def _stale_warning_timestamp(self):
        offset = timedelta(seconds=self.staleness_setting["warning"])
        return self.now - offset

    def _culled_timestamp(self):
        offset = timedelta(seconds=self.staleness_setting["culled"])
        return self.now - offset

    @staticmethod
    def find_host_state(stale_timestamp, stale_warning_timestamp):
        now = datetime.now(UTC)
        if now < stale_timestamp:
            return "fresh"
        if now >= stale_timestamp and now < stale_warning_timestamp:
            return "stale"
        else:
            return "stale warning"


def days_to_seconds(n_days: int) -> int:
    factor = 86400
    return n_days * factor


def seconds_to_days(n_seconds: int) -> int:
    factor = 86400
    return n_seconds // factor


def should_host_stay_fresh_forever(host: "Host") -> bool:
    """
    Check if a host should stay fresh forever (never become stale).
    Currently applies to hosts that have only "rhsm-system-profile-bridge" as a reporter.

    Args:
        host: The host object to check

    Returns:
        bool: True if the host should stay fresh forever, False otherwise
    """
    # If the host has no per_reporter_staleness, it's a new host, and we should check the reporter instead
    if not hasattr(host, "per_reporter_staleness") or not host.per_reporter_staleness:
        return host.reporter == "rhsm-system-profile-bridge"

    reporters = list(host.per_reporter_staleness.keys())
    return len(reporters) == 1 and reporters[0] == "rhsm-system-profile-bridge"
