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

DEFAULT_TOLERANCE = 3600

# Near-default values (within DEFAULT_TOLERANCE of system defaults)
NEAR_DEFAULT_STALE = CONVENTIONAL_TIME_TO_STALE_SECONDS + 100
NEAR_DEFAULT_WARNING = CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - 500
NEAR_DEFAULT_DELETE = CONVENTIONAL_TIME_TO_DELETE_SECONDS + 1000

# Clearly custom values (well outside DEFAULT_TOLERANCE of system defaults)
CUSTOM_STALE = 200000
CUSTOM_WARNING = 700000
CUSTOM_DELETE = 3000000


# ---------------------------------------------------------------------------
# _is_near_default unit tests
# ---------------------------------------------------------------------------


def test_is_near_default_exact_defaults(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="test-org-exact",
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        assert _is_near_default(row, DEFAULT_TOLERANCE) is True


def test_is_near_default_within_tolerance(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="test-org-within",
            conventional_time_to_stale=NEAR_DEFAULT_STALE,
            conventional_time_to_stale_warning=NEAR_DEFAULT_WARNING,
            conventional_time_to_delete=NEAR_DEFAULT_DELETE,
        )
        assert _is_near_default(row, DEFAULT_TOLERANCE) is True


def test_is_near_default_one_field_outside_tolerance(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="test-org-outside",
            conventional_time_to_stale=CUSTOM_STALE,
            conventional_time_to_stale_warning=NEAR_DEFAULT_WARNING,
            conventional_time_to_delete=NEAR_DEFAULT_DELETE,
        )
        assert _is_near_default(row, DEFAULT_TOLERANCE) is False


def test_is_near_default_all_outside_tolerance(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="test-org-all-custom",
            conventional_time_to_stale=CUSTOM_STALE,
            conventional_time_to_stale_warning=CUSTOM_WARNING,
            conventional_time_to_delete=CUSTOM_DELETE,
        )
        assert _is_near_default(row, DEFAULT_TOLERANCE) is False


def test_is_near_default_boundary_exactly_at_tolerance(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="test-org-boundary",
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + DEFAULT_TOLERANCE,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        assert _is_near_default(row, DEFAULT_TOLERANCE) is True


def test_is_near_default_boundary_one_over_tolerance(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="test-org-one-over",
            conventional_time_to_stale=CONVENTIONAL_TIME_TO_STALE_SECONDS + DEFAULT_TOLERANCE + 1,
            conventional_time_to_stale_warning=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            conventional_time_to_delete=CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )
        assert _is_near_default(row, DEFAULT_TOLERANCE) is False


# ---------------------------------------------------------------------------
# run() integration tests
# ---------------------------------------------------------------------------


def _get_staleness_row(org_id):
    return Staleness.query.filter(Staleness.org_id == org_id).one_or_none()


def _add_staleness_row(org_id, stale, warning, delete):
    row = Staleness(
        org_id=org_id,
        conventional_time_to_stale=stale,
        conventional_time_to_stale_warning=warning,
        conventional_time_to_delete=delete,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_run_deletes_near_default_rows(flask_app, monkeypatch):
    """Rows within tolerance are deleted and their cache entries invalidated."""
    org_id = "cleanup-staleness-near-default"
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(DEFAULT_TOLERANCE))

    with flask_app.app.app_context():
        _add_staleness_row(org_id, NEAR_DEFAULT_STALE, NEAR_DEFAULT_WARNING, NEAR_DEFAULT_DELETE)

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(org_id) is None
        mock_cache.delete.assert_called_once_with(org_id)


def test_run_keeps_custom_rows(flask_app, monkeypatch):
    """Rows with any field outside tolerance are kept untouched."""
    org_id = "cleanup-staleness-custom"
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(DEFAULT_TOLERANCE))

    with flask_app.app.app_context():
        _add_staleness_row(org_id, CUSTOM_STALE, CUSTOM_WARNING, CUSTOM_DELETE)

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(org_id) is not None
        mock_cache.delete.assert_not_called()


def test_run_mixed_rows(flask_app, monkeypatch):
    """Near-default rows are deleted; truly custom rows are kept."""
    near_org = "cleanup-staleness-mixed-near"
    custom_org = "cleanup-staleness-mixed-custom"
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(DEFAULT_TOLERANCE))

    with flask_app.app.app_context():
        _add_staleness_row(near_org, NEAR_DEFAULT_STALE, NEAR_DEFAULT_WARNING, NEAR_DEFAULT_DELETE)
        _add_staleness_row(custom_org, CUSTOM_STALE, CUSTOM_WARNING, CUSTOM_DELETE)

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(near_org) is None
        assert _get_staleness_row(custom_org) is not None
        mock_cache.delete.assert_called_once_with(near_org)


def test_run_dry_run_does_not_delete(flask_app, monkeypatch):
    """DRY_RUN=true leaves the DB unchanged and skips cache invalidation."""
    org_id = "cleanup-staleness-dry-run"
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(DEFAULT_TOLERANCE))

    with flask_app.app.app_context():
        _add_staleness_row(org_id, NEAR_DEFAULT_STALE, NEAR_DEFAULT_WARNING, NEAR_DEFAULT_DELETE)

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(org_id) is not None
        mock_cache.delete.assert_not_called()


def test_run_dry_run_defaults_to_true_when_unset(flask_app, monkeypatch):
    """DRY_RUN defaults to true when the env var is not set."""
    org_id = "cleanup-staleness-dry-default"
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(DEFAULT_TOLERANCE))

    with flask_app.app.app_context():
        _add_staleness_row(org_id, NEAR_DEFAULT_STALE, NEAR_DEFAULT_WARNING, NEAR_DEFAULT_DELETE)

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(org_id) is not None
        mock_cache.delete.assert_not_called()


def test_run_no_rows_does_nothing(flask_app, monkeypatch):
    """When the staleness table is empty the job completes without errors."""
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(DEFAULT_TOLERANCE))

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    mock_cache.delete.assert_not_called()


def test_run_custom_tolerance_tighter(flask_app, monkeypatch):
    """A tighter tolerance keeps rows that would be deleted under the default."""
    org_id = "cleanup-staleness-tight-tol"
    tighter_tolerance = 50  # much tighter than DEFAULT_TOLERANCE=3600

    # Row is within DEFAULT_TOLERANCE but outside tighter_tolerance
    stale = CONVENTIONAL_TIME_TO_STALE_SECONDS + 100  # 100 > 50 → outside tight tolerance
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(tighter_tolerance))

    with flask_app.app.app_context():
        _add_staleness_row(
            org_id, stale, CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS, CONVENTIONAL_TIME_TO_DELETE_SECONDS
        )

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(org_id) is not None
        mock_cache.delete.assert_not_called()


def test_run_custom_tolerance_wider(flask_app, monkeypatch):
    """A wider tolerance deletes rows that would be kept under the default."""
    org_id = "cleanup-staleness-wide-tol"
    wider_tolerance = 200000

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", str(wider_tolerance))

    with flask_app.app.app_context():
        # stale is 100000 s from default — outside DEFAULT_TOLERANCE but inside wider_tolerance
        stale = CONVENTIONAL_TIME_TO_STALE_SECONDS + 100000
        _add_staleness_row(
            org_id, stale, CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS, CONVENTIONAL_TIME_TO_DELETE_SECONDS
        )

    session = db.session

    with patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(org_id) is None
        mock_cache.delete.assert_called_once_with(org_id)


def test_run_invalid_tolerance_exits(flask_app, monkeypatch):
    """Non-integer CLEANUP_STALENESS_TOLERANCE causes SystemExit(1)."""
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("CLEANUP_STALENESS_TOLERANCE", "not-a-number")

    session = db.session

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1
