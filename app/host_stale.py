from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.environment import RuntimeEnvironment

RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


class HostStale:
    def __init__(self, staleness, host_type, last_run_secs):
        self.now = datetime.now(timezone.utc)
        self.staleness = staleness
        self.host_type = host_type
        self.last_run_secs = last_run_secs

        self.staleness_host_type = {
            None: {
                "stale": staleness["conventional_time_to_stale"],
                "warning": staleness["conventional_time_to_stale_warning"],
                "culled": staleness["conventional_time_to_delete"],
            },
            "edge": {
                "stale": staleness["immutable_time_to_stale"],
                "warning": staleness["immutable_time_to_stale_warning"],
                "culled": staleness["immutable_time_to_delete"],
            },
        }

    def _stale_timestamp(self):
        offset = timedelta(seconds=self.staleness_host_type[self.host_type]["stale"])
        return self.now - offset

    def _stale_in_last_seconds(self):  # default to 3600s / 1h
        stale = self._stale_timestamp()
        offset = timedelta(seconds=self.last_run_secs)
        return stale - offset

    def stale_in_window(self):
        return self._stale_in_last_seconds(), self._stale_timestamp()
