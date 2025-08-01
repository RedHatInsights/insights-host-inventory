from datetime import datetime
from datetime import timezone

from sqlalchemy import and_

from app.models import Host


class HostStalenessStatesDbFilters:
    def __init__(self):
        self.now = datetime.now(tz=timezone.utc)

    def fresh(self):
        return self.now < Host.stale_timestamp

    def stale(self):
        return and_(self.now >= Host.stale_timestamp, self.now < Host.stale_warning_timestamp)

    def stale_warning(self):
        return and_(self.now >= Host.stale_warning_timestamp, self.now < Host.deletion_timestamp)

    def culled(self):
        return self.now >= Host.deletion_timestamp
