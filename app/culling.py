from collections import namedtuple
from datetime import datetime
from datetime import timedelta
from datetime import timezone

__all__ = ("Conditions", "staleness_to_conditions", "Timestamps")


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
    def __init__(self, staleness, host_type):
        self.now = datetime.now(timezone.utc)
        self.host_type = host_type

        # Build this dictionary dynamically?
        self.staleness_host_type = {
            None: {
                "stale": staleness["conventional_staleness_delta"],
                "warning": staleness["conventional_stale_warning_delta"],
                "culled": staleness["conventional_culling_delta"],
            },
            "edge": {
                "stale": staleness["immutable_staleness_delta"],
                "warning": staleness["immutable_stale_warning_delta"],
                "culled": staleness["immutable_culling_delta"],
            },
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
        offset = timedelta(seconds=self.staleness_host_type[self.host_type]["stale"])
        return self.now - offset

    def _stale_warning_timestamp(self):
        offset = timedelta(seconds=self.staleness_host_type[self.host_type]["warning"])
        return self.now - offset

    def _culled_timestamp(self):
        offset = timedelta(seconds=self.staleness_host_type[self.host_type]["culled"])
        return self.now - offset

    @staticmethod
    def _sub_time(timestamp, delta):
        return timestamp - delta


def staleness_to_conditions(staleness, staleness_states, host_type, timestamp_filter_func):
    _filters = []
    condition = Conditions(staleness, host_type)
    filtered_states = (state for state in staleness_states)
    for state in filtered_states:
        _filters.append(timestamp_filter_func(*getattr(condition, state)(), host_type=host_type))
    return _filters
