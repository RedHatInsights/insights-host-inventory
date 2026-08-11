import logging
from unittest.mock import patch

import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Staleness
from app.models import db
from jobs.cleanup_custom_staleness import _is_near_default
from jobs.cleanup_custom_staleness import run

_logger = logging.getLogger("test_cleanup_custom_staleness")

# One hour in seconds — the tolerance boundary.
ONE_HOUR = 3600

# Offsets that are strictly inside the tolerance window (< 3600 s).
JUST_UNDER = ONE_HOUR - 1  # 3599 s — should be deleted

# Offsets that are exactly at (or beyond) the tolerance boundary (>= 3600 s).
AT_EXACTLY = ONE_HOUR  # 3600 s — must be preserved

ORG_NEAR_DEFAULT = "cleanup-near-default-org"
ORG_EXACTLY_ONE_HOUR = "cleanup-exactly-one-hour-org"
ORG_CUSTOM = "cleanup-custom-org"


# ---------------------------------------------------------------------------
# _is_near_default unit tests
# ---------------------------------------------------------------------------


def _make_row(stale_offset=0, warning_offset=0, delete_offset=0):
    """Create an in-memory Staleness row with offsets from system defaults."""
    return Staleness(
        org_id="dummy",
        conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + stale_offset,
        conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + warning_offset,
        conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS + delete_offset,
    )


def test_is_near_default_exact_defaults():
    """A row identical to system defaults is near-default."""
    assert _is_near_default(_make_row()) is True


def test_is_near_default_just_under_tolerance():
    """All fields within (< 3600 s) → near-default."""
    assert _is_near_default(_make_row(stale_offset=JUST_UNDER, warning_offset=-JUST_UNDER)) is True


def test_is_near_default_exactly_one_hour_stale():
    """Stale field at exactly 3600 s above default → NOT near-default."""
    assert _is_near_default(_make_row(stale_offset=AT_EXACTLY)) is False


def test_is_near_default_exactly_one_hour_warning():
    """Warning field at exactly 3600 s above default → NOT near-default."""
    assert _is_near_default(_make_row(warning_offset=AT_EXACTLY)) is False


def test_is_near_default_exactly_one_hour_delete():
    """Delete field at exactly 3600 s above default → NOT near-default."""
    assert _is_near_default(_make_row(delete_offset=AT_EXACTLY)) is False


def test_is_near_default_one_field_over():
    """Even one field at boundary means the whole row must be kept."""
    assert _is_near_default(_make_row(stale_offset=JUST_UNDER, warning_offset=AT_EXACTLY)) is False


def test_is_near_default_large_custom_values():
    """Genuinely custom values far from defaults → NOT near-default."""
    row = Staleness(
        org_id="dummy",
        conventional_time_to_stale=200000,
        conventional_time_to_stale_warning=700000,
        conventional_time_to_delete=3000000,
    )
    assert _is_near_default(row) is False


# ---------------------------------------------------------------------------
# run() integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_test_orgs(flask_app):
    """Remove any staleness rows created by this module after each test."""
    yield
    with flask_app.app.app_context():
        for org_id in (ORG_NEAR_DEFAULT, ORG_EXACTLY_ONE_HOUR, ORG_CUSTOM):
            row = Staleness.query.filter(Staleness.org_id == org_id).one_or_none()
            if row:
                db.session.delete(row)
        db.session.commit()


def _get_row(org_id):
    return Staleness.query.filter(Staleness.org_id == org_id).one_or_none()


def test_run_deletes_near_default_row(flask_app, monkeypatch):
    """Near-default rows (< 3600 s on all fields) are deleted in live mode."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        row = Staleness(
            org_id=ORG_NEAR_DEFAULT,
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + JUST_UNDER,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        db.session.add(row)
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_row(ORG_NEAR_DEFAULT) is None
        mock_cache.delete.assert_called_once_with(ORG_NEAR_DEFAULT)


def test_run_preserves_exactly_one_hour_row(flask_app, monkeypatch):
    """Rows where any field differs by exactly 3600 s are preserved."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        row = Staleness(
            org_id=ORG_EXACTLY_ONE_HOUR,
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + AT_EXACTLY,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        db.session.add(row)
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_row(ORG_EXACTLY_ONE_HOUR) is not None
        mock_cache.delete.assert_not_called()


def test_run_preserves_genuinely_custom_row(flask_app, monkeypatch):
    """Genuinely custom rows (large deviation) are never deleted."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        row = Staleness(
            org_id=ORG_CUSTOM,
            conventional_time_to_stale=200000,
            conventional_time_to_stale_warning=700000,
            conventional_time_to_delete=3000000,
        )
        db.session.add(row)
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_row(ORG_CUSTOM) is not None
        mock_cache.delete.assert_not_called()


def test_run_mixed_table_only_deletes_near_default(flask_app, monkeypatch):
    """Mixed table: only near-default rows are removed; others remain."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        near_row = Staleness(
            org_id=ORG_NEAR_DEFAULT,
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        boundary_row = Staleness(
            org_id=ORG_EXACTLY_ONE_HOUR,
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + AT_EXACTLY,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        custom_row = Staleness(
            org_id=ORG_CUSTOM,
            conventional_time_to_stale=200000,
            conventional_time_to_stale_warning=700000,
            conventional_time_to_delete=3000000,
        )
        db.session.add_all([near_row, boundary_row, custom_row])
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_row(ORG_NEAR_DEFAULT) is None
        assert _get_row(ORG_EXACTLY_ONE_HOUR) is not None
        assert _get_row(ORG_CUSTOM) is not None
        mock_cache.delete.assert_called_once_with(ORG_NEAR_DEFAULT)


def test_run_dry_run_leaves_all_rows_intact(flask_app, monkeypatch):
    """DRY_RUN=true leaves all rows intact and suppresses cache invalidation."""
    monkeypatch.setenv("DRY_RUN", "true")

    with flask_app.app.app_context():
        row = Staleness(
            org_id=ORG_NEAR_DEFAULT,
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        db.session.add(row)
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_row(ORG_NEAR_DEFAULT) is not None
        mock_cache.delete.assert_not_called()


def test_run_dry_run_defaults_to_true_when_unset(flask_app, monkeypatch):
    """DRY_RUN defaults to true when the env var is absent."""
    monkeypatch.delenv("DRY_RUN", raising=False)

    with flask_app.app.app_context():
        row = Staleness(
            org_id=ORG_NEAR_DEFAULT,
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        db.session.add(row)
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_row(ORG_NEAR_DEFAULT) is not None
        mock_cache.delete.assert_not_called()


def test_run_cache_delete_called_per_deleted_row(flask_app, monkeypatch):
    """StalenessCache.delete is called exactly once per deleted row."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        for org_id in (ORG_NEAR_DEFAULT, ORG_EXACTLY_ONE_HOUR):
            row = Staleness(
                org_id=org_id,
                conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS,
                conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
                conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
            )
            db.session.add(row)
        db.session.commit()

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    # Both rows are near-default (identical to system defaults), so both should be deleted
    assert mock_cache.delete.call_count == 2




# ---------------------------------------------------------------------------
# SUSPEND_JOB integration test
# ---------------------------------------------------------------------------


def test_suspend_job_exits_immediately_with_code_zero(monkeypatch):
    """When SUSPEND_JOB env var is 'true', the __main__ entry-point exits with code 0."""
    import runpy

    monkeypatch.setenv("SUSPEND_JOB", "true")
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("jobs.cleanup_custom_staleness", run_name="__main__")
    assert exc_info.value.code == 0
