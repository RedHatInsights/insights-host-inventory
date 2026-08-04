import logging
from unittest.mock import patch

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Staleness
from app.models import db
from jobs.clean_custom_staleness import run

_logger = logging.getLogger("test_clean_custom_staleness")

# Tolerance boundary: differences < 3600s → equivalent; >= 3600s → custom.
_TOLERANCE = 3600


def _make_staleness(org_id: str, stale: int, warning: int, delete: int) -> Staleness:
    row = Staleness(
        org_id=org_id,
        conventional_time_to_stale=stale,
        conventional_time_to_stale_warning=warning,
        conventional_time_to_delete=delete,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _row_exists(org_id: str) -> bool:
    return Staleness.query.filter(Staleness.org_id == org_id).one_or_none() is not None


# ---------------------------------------------------------------------------
# test_run_deletes_equivalent_rows
# ---------------------------------------------------------------------------


def test_run_deletes_equivalent_rows(flask_app, monkeypatch):
    """A row with exact default values is deleted when DRY_RUN=false."""
    org_id = "clean-staleness-exact-defaults"
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _make_staleness(
            org_id,
            CONVENTIONAL_TIME_TO_STALE_SECONDS,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        assert _row_exists(org_id)

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert not _row_exists(org_id)
        mock_cache.delete.assert_called_once_with(org_id)


# ---------------------------------------------------------------------------
# test_run_deletes_near_default_rows
# ---------------------------------------------------------------------------


def test_run_deletes_near_default_rows(flask_app, monkeypatch):
    """A row with all values offset by 3599s (within tolerance) is deleted."""
    org_id = "clean-staleness-near-defaults"
    monkeypatch.setenv("DRY_RUN", "false")

    offset = _TOLERANCE - 1  # 3599 — strictly less than tolerance

    with flask_app.app.app_context():
        _make_staleness(
            org_id,
            CONVENTIONAL_TIME_TO_STALE_SECONDS + offset,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + offset,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS + offset,
        )

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert not _row_exists(org_id)
        mock_cache.delete.assert_called_once_with(org_id)


# ---------------------------------------------------------------------------
# test_run_retains_custom_rows  (boundary: exactly 3600s offset)
# ---------------------------------------------------------------------------


def test_run_retains_custom_rows(flask_app, monkeypatch):
    """A row with values at exactly 3600s offset is NOT deleted (boundary)."""
    org_id = "clean-staleness-boundary-offset"
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _make_staleness(
            org_id,
            CONVENTIONAL_TIME_TO_STALE_SECONDS + _TOLERANCE,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + _TOLERANCE,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS + _TOLERANCE,
        )

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _row_exists(org_id)
        mock_cache.delete.assert_not_called()


# ---------------------------------------------------------------------------
# test_run_retains_truly_custom_rows
# ---------------------------------------------------------------------------


def test_run_retains_truly_custom_rows(flask_app, monkeypatch):
    """A row with values far from defaults is retained."""
    org_id = "clean-staleness-truly-custom"
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _make_staleness(
            org_id,
            200000,  # far from CONVENTIONAL_TIME_TO_STALE_SECONDS = 104400
            700000,
            3000000,
        )

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _row_exists(org_id)
        mock_cache.delete.assert_not_called()


# ---------------------------------------------------------------------------
# test_run_mixed_rows
# ---------------------------------------------------------------------------


def test_run_mixed_rows(flask_app, monkeypatch):
    """Equivalent row is deleted; custom row is retained."""
    eq_org = "clean-staleness-mixed-equivalent"
    custom_org = "clean-staleness-mixed-custom"
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _make_staleness(
            eq_org,
            CONVENTIONAL_TIME_TO_STALE_SECONDS,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        _make_staleness(
            custom_org,
            200000,
            700000,
            3000000,
        )

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert not _row_exists(eq_org)
        assert _row_exists(custom_org)
        mock_cache.delete.assert_called_once_with(eq_org)


# ---------------------------------------------------------------------------
# test_run_dry_run_no_deletions
# ---------------------------------------------------------------------------


def test_run_dry_run_no_deletions(flask_app, monkeypatch):
    """With DRY_RUN=true, no rows are deleted and cache.delete is not called."""
    org_id = "clean-staleness-dry-run"
    monkeypatch.setenv("DRY_RUN", "true")

    with flask_app.app.app_context():
        _make_staleness(
            org_id,
            CONVENTIONAL_TIME_TO_STALE_SECONDS,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _row_exists(org_id)
        mock_cache.delete.assert_not_called()


# ---------------------------------------------------------------------------
# test_run_dry_run_defaults_to_true
# ---------------------------------------------------------------------------


def test_run_dry_run_defaults_to_true(flask_app, monkeypatch):
    """When DRY_RUN env var is absent, it defaults to true (no deletions)."""
    org_id = "clean-staleness-dry-run-default"
    monkeypatch.delenv("DRY_RUN", raising=False)

    with flask_app.app.app_context():
        _make_staleness(
            org_id,
            CONVENTIONAL_TIME_TO_STALE_SECONDS,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _row_exists(org_id)
        mock_cache.delete.assert_not_called()


# ---------------------------------------------------------------------------
# test_run_no_rows
# ---------------------------------------------------------------------------


def test_run_no_rows(flask_app, monkeypatch):
    """Running with an empty staleness table causes no errors."""
    monkeypatch.setenv("DRY_RUN", "false")

    with patch("jobs.clean_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, db.session, flask_app)

    mock_cache.delete.assert_not_called()
