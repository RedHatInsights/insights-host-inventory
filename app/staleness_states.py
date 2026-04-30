from datetime import UTC
from datetime import datetime
from datetime import timedelta

from sqlalchemy import and_
from sqlalchemy import or_

from app.models import Host


class HostStalenessStatesDbFilters:
    """Host-level staleness predicates for SQL filtering.

    Boundaries match ``Timestamps`` / ``get_staleness_timestamps``: ``last_check_in``
    plus the org's ``conventional_time_to_*`` seconds.
    """

    def __init__(self, staleness: dict):
        self.now = datetime.now(tz=UTC)
        self._stale_sec = staleness["conventional_time_to_stale"]
        self._warn_sec = staleness["conventional_time_to_stale_warning"]
        self._delete_sec = staleness["conventional_time_to_delete"]

    def _computed_stale_boundary(self):
        return Host.last_check_in + timedelta(seconds=self._stale_sec)

    def _computed_stale_warning_boundary(self):
        return Host.last_check_in + timedelta(seconds=self._warn_sec)

    def _computed_deletion_boundary(self):
        return Host.last_check_in + timedelta(seconds=self._delete_sec)

    def _computed_basis(self):
        return and_(Host.stale_timestamp.is_(None), Host.last_check_in.isnot(None))

    def fresh(self):
        persisted = and_(Host.stale_timestamp.isnot(None), self.now < Host.stale_timestamp)
        computed = and_(self._computed_basis(), self.now < self._computed_stale_boundary())
        # No reference time when both are NULL; retain prior behavior (included as non-culled listing).
        no_reference = and_(Host.stale_timestamp.is_(None), Host.last_check_in.is_(None))
        return or_(persisted, computed, no_reference)

    def stale(self):
        persisted = and_(
            Host.stale_timestamp.isnot(None),
            Host.stale_warning_timestamp.isnot(None),
            self.now >= Host.stale_timestamp,
            self.now < Host.stale_warning_timestamp,
        )
        computed = and_(
            self._computed_basis(),
            self.now >= self._computed_stale_boundary(),
            self.now < self._computed_stale_warning_boundary(),
        )
        return or_(persisted, computed)

    def stale_warning(self):
        persisted = and_(
            Host.stale_warning_timestamp.isnot(None),
            Host.deletion_timestamp.isnot(None),
            self.now >= Host.stale_warning_timestamp,
            self.now < Host.deletion_timestamp,
        )
        computed = and_(
            self._computed_basis(),
            self.now >= self._computed_stale_warning_boundary(),
            self.now < self._computed_deletion_boundary(),
        )
        return or_(persisted, computed)

    def culled(self):
        persisted = and_(Host.deletion_timestamp.isnot(None), self.now >= Host.deletion_timestamp)
        computed = and_(self._computed_basis(), self.now >= self._computed_deletion_boundary())
        return or_(persisted, computed)
