"""Unit tests for lib.staleness default-equivalence helpers (RHINENG-20674)."""

import pytest

from app.auth.identity import Identity
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from lib.staleness import staleness_equivalent_to_system_defaults
from tests.helpers.test_utils import USER_IDENTITY


@pytest.mark.parametrize(
    "offset_seconds, expect_equivalent",
    [
        (0, True),
        (3599, True),
        (-3599, True),
        (3600, False),
        (-3600, False),
        (3601, False),
        (-3601, False),
    ],
)
def test_staleness_equivalent_to_system_defaults_boundaries(flask_app, offset_seconds, expect_equivalent):
    """Each field is offset from its default; all three use the same offset (ordering preserved)."""
    identity = Identity(USER_IDENTITY)
    with flask_app.app.app_context():
        triple = {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + offset_seconds,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + offset_seconds,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + offset_seconds,
        }
        assert staleness_equivalent_to_system_defaults(triple, identity) is expect_equivalent


def test_staleness_equivalent_incomplete_payload_returns_false(flask_app):
    """Missing keys are not treated as matching defaults (defensive, pre-merge callers)."""
    with flask_app.app.app_context():
        assert not staleness_equivalent_to_system_defaults(
            {"conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS},
            Identity(USER_IDENTITY),
        )
