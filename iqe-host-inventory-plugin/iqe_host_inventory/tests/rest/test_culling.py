# REVISIT: Temporarily restoring a portion of this file since some other modules
# rely on it.  Once those modules are updated, this file can be deleted.
from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from random import randint
from typing import Protocol

import pytest

pytestmark = [pytest.mark.backend]
STALE_WARNING_DAYS = 7
CULLED_DAYS = 30


def gen_fresh_date(tz: timezone = UTC) -> datetime:
    """Generate some future date for "fresh" host."""
    return datetime.now(tz) + timedelta(days=randint(1, 7))


def gen_stale_date(tz: timezone = UTC) -> datetime:
    """Generate "stale" host date - STALE_WARNING_DAYS < date < now()"""
    return datetime.now(tz) - timedelta(days=randint(1, STALE_WARNING_DAYS - 1))


def gen_stale_warning_date(tz: timezone = UTC) -> datetime:
    """Generate "stale_warning" host date - now()-CULLED_DAYS < date < now()-STALE_WARNING_DAYS"""
    return datetime.now(tz) - timedelta(days=randint(STALE_WARNING_DAYS, CULLED_DAYS - 1))


def gen_culled_date(tz: timezone = UTC) -> datetime:
    """Generate "stale_warning" host date - now()-CULLED_DAYS-7 < date < now()-CULLED_DAYS"""
    return datetime.now(tz) - timedelta(days=randint(CULLED_DAYS, CULLED_DAYS + 7))


def as_utc_isoformat(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat()


class CallProtocol(Protocol):
    def __call__(self, tz: timezone = UTC) -> datetime: ...


gen_dates: dict[str, CallProtocol] = {
    "fresh": gen_fresh_date,
    "stale": gen_stale_date,
    "stale_warning": gen_stale_warning_date,
    "culled": gen_culled_date,
}


def gen_date_by_state(state: str = "fresh"):
    return gen_dates[state]()
