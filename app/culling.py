from collections import namedtuple
from datetime import datetime
from datetime import timedelta
from datetime import timezone

__all__ = ("Conditions", "staleness_to_conditions", "Timestamps")


class _Config(namedtuple("_Config", ("stale_warning_offset_days", "culled_offset_days"))):
    @classmethod
    def from_config(cls, config):
        return cls(config.culling_stale_warning_offset_days, config.culling_culled_offset_days)


class _WithConfig:
    def __init__(self, config):
        self.config = config

    @classmethod
    def from_config(cls, config):
        config = _Config.from_config(config)
        return cls(config)


class Timestamps(_WithConfig):
    @staticmethod
    def _add_days(timestamp, days):
        return timestamp + timedelta(days=days)

    def stale_timestamp(self, stale_timestamp):
        return self._add_days(stale_timestamp, 0)

    def stale_warning_timestamp(self, stale_timestamp):
        return self._add_days(stale_timestamp, self.config.stale_warning_offset_days)

    def culled_timestamp(self, stale_timestamp):
        return self._add_days(stale_timestamp, self.config.culled_offset_days)


class Conditions(_WithConfig):
    def __init__(self, config):
        super().__init__(config)
        self.now = datetime.now(timezone.utc)

    @staticmethod
    def _sub_days(timestamp, days):
        return timestamp - timedelta(days=days)

    def fresh(self):
        return self.now, None

    def stale(self):
        return self._stale_warning_timestamp(), self.now

    def stale_warning(self):
        return self._culled_timestamp(), self._stale_warning_timestamp()

    def culled(self):
        return None, self._culled_timestamp()

    def _stale_warning_timestamp(self):
        offset = timedelta(days=self.config.stale_warning_offset_days)
        return self.now - offset

    def _culled_timestamp(self):
        offset = timedelta(days=self.config.culled_offset_days)
        return self.now - offset


def staleness_to_conditions(config, staleness, timestamp_filter_func):
    condition = Conditions.from_config(config)
    filtered_states = (state for state in staleness if state not in ("unknown",))
    return (timestamp_filter_func(*getattr(condition, state)()) for state in filtered_states)
