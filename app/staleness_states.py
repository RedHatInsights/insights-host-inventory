from datetime import datetime
from datetime import timezone

from sqlalchemy import and_

from app.models import Host


class HostStalenessStatesDbFilters:
    def __init__(self, now=None):
        self.now = now if now is not None else datetime.now(tz=timezone.utc)

    def fresh(self):
        return and_(self.now < Host.stale_timestamp, self.now < Host.deletion_timestamp)

    def stale(self):
        return and_(
            self.now >= Host.stale_timestamp,
            self.now < Host.stale_warning_timestamp,
            self.now < Host.deletion_timestamp,
        )

    def stale_warning(self):
        return and_(self.now >= Host.stale_warning_timestamp, self.now < Host.deletion_timestamp)

    def culled(self):
        return self.now >= Host.deletion_timestamp
