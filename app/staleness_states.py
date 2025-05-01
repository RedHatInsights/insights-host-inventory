from datetime import datetime
from datetime import timezone

from app.models import Host


class HostStalenessStatesDbFilters:
    def __init__(self):
        self.now = datetime.now(tz=timezone.utc)

    def fresh(self):
        return self.now < Host.stale_timestamp

    def stale(self):
        return self.now >= Host.stale_timestamp

    def stale_warning(self):
        return self.now >= Host.stale_warning_timestamp

    def culled(self):
        return self.now >= Host.deletion_timestamp
