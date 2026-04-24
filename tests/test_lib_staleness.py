"""Unit tests for lib/staleness.py helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from lib.staleness import NEAR_DEFAULT_THRESHOLD_SECONDS
from lib.staleness import is_staleness_near_default


def _dict(stale=None, warning=None, delete=None) -> dict:
    return {
        "conventional_time_to_stale": stale if stale is not None else CONVENTIONAL_TIME_TO_STALE_SECONDS,
        "conventional_time_to_stale_warning": (
            warning if warning is not None else CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
        ),
        "conventional_time_to_delete": delete if delete is not None else CONVENTIONAL_TIME_TO_DELETE_SECONDS,
    }


def _obj(stale=None, warning=None, delete=None) -> SimpleNamespace:
    return SimpleNamespace(
        conventional_time_to_stale=stale if stale is not None else CONVENTIONAL_TIME_TO_STALE_SECONDS,
        conventional_time_to_stale_warning=(
            warning if warning is not None else CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
        ),
        conventional_time_to_delete=delete if delete is not None else CONVENTIONAL_TIME_TO_DELETE_SECONDS,
    )


class TestIsStatelessNearDefault:
    # --- dict inputs ---

    def test_exact_defaults_dict(self):
        assert is_staleness_near_default(_dict()) is True

    def test_within_threshold_dict(self):
        assert (
            is_staleness_near_default(
                _dict(
                    stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + NEAR_DEFAULT_THRESHOLD_SECONDS,
                    warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - NEAR_DEFAULT_THRESHOLD_SECONDS,
                    delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS + NEAR_DEFAULT_THRESHOLD_SECONDS,
                )
            )
            is True
        )

    def test_one_second_over_threshold_dict(self):
        assert (
            is_staleness_near_default(
                _dict(stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + NEAR_DEFAULT_THRESHOLD_SECONDS + 1)
            )
            is False
        )

    def test_far_outside_threshold_dict(self):
        assert is_staleness_near_default(_dict(stale=1)) is False

    def test_only_one_field_outside_threshold_dict(self):
        assert is_staleness_near_default(_dict(delete=1)) is False

    # --- model object inputs ---

    def test_exact_defaults_obj(self):
        assert is_staleness_near_default(_obj()) is True

    def test_within_threshold_obj(self):
        assert (
            is_staleness_near_default(_obj(stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + NEAR_DEFAULT_THRESHOLD_SECONDS))
            is True
        )

    def test_far_outside_threshold_obj(self):
        assert is_staleness_near_default(_obj(warning=1)) is False
