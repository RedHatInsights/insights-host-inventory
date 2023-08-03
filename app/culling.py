from collections import namedtuple
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app import inventory_config

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

    def stale_timestamp(self, stale_timestamp):
        return self._add_time(stale_timestamp, timedelta(days=0))

    def stale_warning_timestamp(self, stale_timestamp):
        return self._add_time(stale_timestamp, self.config.stale_warning_offset_delta)

    def culled_timestamp(self, stale_timestamp):
        return self._add_time(stale_timestamp, self.config.culled_offset_delta)


class Conditions(_WithConfig):
    def __init__(self, config):
        super().__init__(config)
        self.now = datetime.now(timezone.utc)

    @staticmethod
    def _sub_time(timestamp, delta):
        return timestamp - delta

    def fresh(self):
        return self.now, None

    def stale(self):
        return self._stale_warning_timestamp(), self.now

    def stale_warning(self):
        return self._culled_timestamp(), self._stale_warning_timestamp()

    def culled(self):
        return None, self._culled_timestamp()

    def _stale_warning_timestamp(self):
        offset = self.config.stale_warning_offset_delta
        return self.now - offset

    def _culled_timestamp(self):
        offset = self.config.culled_offset_delta
        return self.now - offset


def staleness_to_conditions(config, staleness, timestamp_filter_func):
    condition = Conditions.from_config(config)
    filtered_states = (state for state in staleness if state not in ("unknown",))
    return (timestamp_filter_func(*getattr(condition, state)()) for state in filtered_states)


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def build_acc_staleness_sys_default(org_id, account):
    config = inventory_config()
    return AttrDict(
        {
            "id": "system_default",
            "account": account,
            "org_id": org_id,
            "conventional_staleness_delta": config.conventional_staleness_seconds,
            "conventional_stale_warning_delta": config.conventional_stale_warning_seconds,
            "conventional_culling_delta": config.conventional_culling_seconds,
            "immutable_staleness_delta": config.immutable_staleness_seconds,
            "immutable_stale_warning_delta": config.immutable_stale_warning_seconds,
            "immutable_culling_delta": config.immutable_culling_seconds,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
