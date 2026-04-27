"""Conventional staleness triples shared by account/staleness API tests (RHINENG-20674)."""

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS

# Differs from system defaults by more than one hour (custom row in DB)
CUSTOM_STALENESS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 5000,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 5000,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 5000,
}

# +3599s on every field — still equivalent to defaults
JUST_UNDER_ONE_HOUR = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 3599,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 3599,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 3599,
}

# Exactly +1h on every field — not default-equivalent
AT_EXACTLY_ONE_HOUR = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 3600,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 3600,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 3600,
}


def assert_staleness_row_matches_triple(row, triple: dict[str, int]) -> None:
    """Assert a persisted ``Staleness`` row matches a conventional triple dict."""
    assert row.conventional_time_to_stale == triple["conventional_time_to_stale"]
    assert row.conventional_time_to_stale_warning == triple["conventional_time_to_stale_warning"]
    assert row.conventional_time_to_delete == triple["conventional_time_to_delete"]
