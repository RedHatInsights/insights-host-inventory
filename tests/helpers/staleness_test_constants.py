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

# Slightly off defaults; strictly < 1h per field (equivalent to system defaults, no row)
NEAR_DEFAULT_STALENESS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 100,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 100,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 100,
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

# +3601s on every field — not default-equivalent
BEYOND_TOLERANCE_STALENESS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 3601,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 3601,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 3601,
}
