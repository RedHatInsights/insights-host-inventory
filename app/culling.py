from collections import namedtuple
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from flask import current_app


__all__ = ("StalenessOffset", "StalenessMap")


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


class StalenessMap:
    def __init__(self):
        self.now = datetime.now(timezone.utc)
        self.config = current_app.config["INVENTORY_CONFIG"]

    def fresh(self):
        return self.now, None

    def stale(self):
        return self._stale_warning_timestamp(), self.now

    def stale_warning(self):
        return self._culled_timestamp(), self._stale_warning_timestamp()

    def _stale_warning_timestamp(self):
        offset = timedelta(days=self.config.culling_stale_warning_offset_days)
        return self.now - offset

    def _culled_timestamp(self):
        offset = timedelta(days=self.config.culling_culled_offset_days)
        return self.now - offset
