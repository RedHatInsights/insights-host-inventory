from collections import namedtuple
from datetime import timedelta


__all__ = ("StalenessOffset",)


class StalenessOffset(namedtuple("StalenessOffset", ("stale_warning_offset_days", "culled_offset_days"))):
    @classmethod
    def from_config(cls, config):
        return cls(config.culling_stale_warning_offset_days, config.culling_culled_offset_days)

    @staticmethod
    def _add_days(timestamp, days):
        return timestamp + timedelta(days=days)

    def stale_timestamp(self, stale_timestamp):
        return self._add_days(stale_timestamp, 0)

    def stale_warning_timestamp(self, stale_timestamp):
        return self._add_days(stale_timestamp, self.stale_warning_offset_days)

    def culled_timestamp(self, stale_timestamp):
        return self._add_days(stale_timestamp, self.culled_offset_days)
