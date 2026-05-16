from datetime import UTC
from datetime import datetime
from datetime import timedelta

from sqlalchemy import and_

from app.models import Host


class HostStalenessStatesDbFilters:
    """Host-level staleness predicates for SQL filtering.

    Always derived from ``last_check_in`` plus the org's ``conventional_time_to_*``
    seconds (same as ``Timestamps`` / ``get_staleness_timestamps``).
    """

    def __init__(self, staleness: dict):
        self.now = datetime.now(tz=UTC)
        self._stale_sec = staleness["conventional_time_to_stale"]
        self._warn_sec = staleness["conventional_time_to_stale_warning"]
        self._delete_sec = staleness["conventional_time_to_delete"]

    def _stale_boundary(self):
        return Host.last_check_in + timedelta(seconds=self._stale_sec)

    def _stale_warning_boundary(self):
        return Host.last_check_in + timedelta(seconds=self._warn_sec)

    def _deletion_boundary(self):
        return Host.last_check_in + timedelta(seconds=self._delete_sec)

    def fresh(self):
        return self.now < self._stale_boundary()

    def stale(self):
        return and_(self.now >= self._stale_boundary(), self.now < self._stale_warning_boundary())

    def stale_warning(self):
        return and_(self.now >= self._stale_warning_boundary(), self.now < self._deletion_boundary())

    def culled(self):
        return self.now >= self._deletion_boundary()
