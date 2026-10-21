from datetime import UTC
from datetime import datetime
from datetime import timedelta

from sqlalchemy import and_
from sqlalchemy import false
from sqlalchemy import or_

from app.models import Host

CANONICAL_STATES = ("fresh", "stale", "stale_warning", "culled")


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

    def _boundary(self, boundary_idx: int):
        if boundary_idx == 1:
            return self._stale_boundary()
        elif boundary_idx == 2:
            return self._stale_warning_boundary()
        elif boundary_idx == 3:
            return self._deletion_boundary()
        raise ValueError(f"Invalid boundary index {boundary_idx}")

    def fresh(self):
        return self.now < self._stale_boundary()

    def stale(self):
        return and_(self.now >= self._stale_boundary(), self.now < self._stale_warning_boundary())

    def stale_warning(self):
        return and_(self.now >= self._stale_warning_boundary(), self.now < self._deletion_boundary())

    def culled(self):
        return self.now >= self._deletion_boundary()

    def combined_filter(self, states: list[str] | tuple[str, ...]):
        if not states:
            return false()

        present_indices = sorted({CANONICAL_STATES.index(s) for s in states if s in CANONICAL_STATES})
        # Any non-canonical state names (not in CANONICAL_STATES) are handled
        # individually via a same-named method, e.g. self.some_state().
        # In practice callers strip "unknown" before reaching here, so this
        # list is normally empty; it exists as a safety net for future states.
        other_states = [s for s in dict.fromkeys(states) if s not in CANONICAL_STATES]

        runs: list[list[int]] = []
        for idx in present_indices:
            if not runs or idx != runs[-1][-1] + 1:
                runs.append([idx])
            else:
                runs[-1].append(idx)

        conditions = []
        for run in runs:
            start, end = run[0], run[-1]
            if start == 0 and end == 3:
                conditions.append(Host.last_check_in.isnot(None))
            elif start == 0:
                conditions.append(self.now < self._boundary(end + 1))
            elif end == 3:
                conditions.append(self.now >= self._boundary(start))
            else:
                conditions.append(and_(self.now >= self._boundary(start), self.now < self._boundary(end + 1)))

        for state in other_states:
            conditions.append(getattr(self, state)())

        if not conditions:
            return false()
        if len(conditions) == 1:
            return conditions[0]
        return or_(*conditions)
