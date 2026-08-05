import logging
from contextlib import contextmanager
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from jobs.cleanup_custom_staleness import _is_near_default
from jobs.cleanup_custom_staleness import run
from tests.helpers.staleness_test_constants import AT_EXACTLY_ONE_HOUR
from tests.helpers.staleness_test_constants import CUSTOM_STALENESS
from tests.helpers.staleness_test_constants import JUST_UNDER_ONE_HOUR

_logger = logging.getLogger("test_cleanup_custom_staleness")


# ---------------------------------------------------------------------------
# Minimal stand-in for a Staleness ORM row used in all tests
# ---------------------------------------------------------------------------


class _FakeRow:
    """Minimal stand-in for a Staleness row used in pure-logic unit tests."""

    def __init__(self, org_id, stale, stale_warning, delete):
        self.org_id = org_id
        self.conventional_time_to_stale = stale
        self.conventional_time_to_stale_warning = stale_warning
        self.conventional_time_to_delete = delete


def _make_row(org_id, triple):
    return _FakeRow(
        org_id,
        triple["conventional_time_to_stale"],
        triple["conventional_time_to_stale_warning"],
        triple["conventional_time_to_delete"],
    )


# ---------------------------------------------------------------------------
# Fixtures shared by run() tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_session():
    """Return a MagicMock that mimics an SQLAlchemy Session."""
    session = MagicMock()
    # Default: no rows in the staleness table
    session.query.return_value.all.return_value = []
    return session


@pytest.fixture()
def mock_app():
    """Return a MagicMock FlaskApp whose app_context() is a no-op context manager."""
    app = MagicMock()

    @contextmanager
    def _app_context():
        yield

    app.app.app_context.side_effect = _app_context
    return app


# ---------------------------------------------------------------------------
# Helper: patch StalenessCache *and* session_guard inside the job module
# ---------------------------------------------------------------------------


@contextmanager
def _patched_run_env(rows, dry_run_value, monkeypatch, session, app):
    """
    Set DRY_RUN, configure session rows, and patch StalenessCache + session_guard.

    Yields the mock_cache so callers can assert on it.
    """
    if dry_run_value is None:
        monkeypatch.delenv("DRY_RUN", raising=False)
    else:
        monkeypatch.setenv("DRY_RUN", dry_run_value)

    session.query.return_value.all.return_value = rows

    @contextmanager
    def _fake_session_guard(sess, close=True):  # noqa: ARG001
        yield sess

    with (
        patch("jobs.cleanup_custom_staleness.StalenessCache") as mock_cache,
        patch("jobs.cleanup_custom_staleness.session_guard", side_effect=_fake_session_guard),
    ):
        run(_logger, session, app)
        yield mock_cache


# ===========================================================================
# _is_near_default unit tests
# ===========================================================================


def test_is_near_default_with_exact_defaults():
    row = _FakeRow(
        "org-exact-defaults",
        CONVENTIONAL_TIME_TO_STALE_SECONDS,
        CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
        CONVENTIONAL_TIME_TO_DELETE_SECONDS,
    )
    assert _is_near_default(row) is True


def test_is_near_default_just_under_one_hour():
    row = _make_row("org-just-under", JUST_UNDER_ONE_HOUR)
    assert _is_near_default(row) is True


def test_is_near_default_at_exactly_one_hour():
    row = _make_row("org-exactly-one-hour", AT_EXACTLY_ONE_HOUR)
    assert _is_near_default(row) is False


def test_is_near_default_custom():
    row = _make_row("org-custom", CUSTOM_STALENESS)
    assert _is_near_default(row) is False


def test_is_near_default_one_field_outside():
    """All fields near default except delete — must be retained."""
    row = _FakeRow(
        "org-one-field-outside",
        CONVENTIONAL_TIME_TO_STALE_SECONDS,
        CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
        CONVENTIONAL_TIME_TO_DELETE_SECONDS + 5000,
    )
    assert _is_near_default(row) is False


def test_is_near_default_negative_offset():
    """Values below defaults but within tolerance are still near-default."""
    row = _FakeRow(
        "org-negative-offset",
        CONVENTIONAL_TIME_TO_STALE_SECONDS - 3599,
        CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - 3599,
        CONVENTIONAL_TIME_TO_DELETE_SECONDS - 3599,
    )
    assert _is_near_default(row) is True


def test_is_near_default_exactly_one_hour_negative():
    """Values exactly -3600 from defaults are NOT eligible (boundary is strict <)."""
    row = _FakeRow(
        "org-negative-exactly-one-hour",
        CONVENTIONAL_TIME_TO_STALE_SECONDS - 3600,
        CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - 3600,
        CONVENTIONAL_TIME_TO_DELETE_SECONDS - 3600,
    )
    assert _is_near_default(row) is False


# ===========================================================================
# run() integration tests — fully mocked (no real DB required)
# ===========================================================================


def test_run_deletes_near_default_row(mock_session, mock_app, monkeypatch):
    """A row within tolerance is deleted and the cache is invalidated."""
    row = _make_row("run-delete-near-default", JUST_UNDER_ONE_HOUR)

    with _patched_run_env(
        [row], dry_run_value="false", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_called_once_with(row)
        mock_cache.delete.assert_called_once_with("run-delete-near-default")


def test_run_retains_custom_row(mock_session, mock_app, monkeypatch):
    """A row with custom (far-from-default) values is never deleted."""
    row = _make_row("run-retain-custom", CUSTOM_STALENESS)

    with _patched_run_env(
        [row], dry_run_value="false", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_not_called()
        mock_cache.delete.assert_not_called()


def test_run_retains_at_exactly_one_hour(mock_session, mock_app, monkeypatch):
    """A row exactly at the 3600 s boundary is retained (boundary is strict <)."""
    row = _make_row("run-retain-exactly-one-hour", AT_EXACTLY_ONE_HOUR)

    with _patched_run_env(
        [row], dry_run_value="false", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_not_called()
        mock_cache.delete.assert_not_called()


def test_run_dry_run_does_not_delete(mock_session, mock_app, monkeypatch):
    """DRY_RUN=true prevents deletion even for near-default rows."""
    row = _make_row("run-dry-run-no-delete", JUST_UNDER_ONE_HOUR)

    with _patched_run_env(
        [row], dry_run_value="true", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_not_called()
        mock_cache.delete.assert_not_called()


def test_run_dry_run_defaults_to_true(mock_session, mock_app, monkeypatch):
    """When DRY_RUN is unset the job defaults to dry-run mode and writes nothing."""
    row = _make_row("run-dry-run-default", JUST_UNDER_ONE_HOUR)

    with _patched_run_env(
        [row], dry_run_value=None, monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_not_called()
        mock_cache.delete.assert_not_called()


def test_run_mixed_rows(mock_session, mock_app, monkeypatch):
    """Near-default rows are deleted; custom rows are retained."""
    row_near = _make_row("run-mixed-near-default", JUST_UNDER_ONE_HOUR)
    row_custom = _make_row("run-mixed-custom", CUSTOM_STALENESS)

    with _patched_run_env(
        [row_near, row_custom],
        dry_run_value="false",
        monkeypatch=monkeypatch,
        session=mock_session,
        app=mock_app,
    ) as mock_cache:
        mock_session.delete.assert_called_once_with(row_near)
        mock_cache.delete.assert_called_once_with("run-mixed-near-default")


def test_run_no_rows(mock_session, mock_app, monkeypatch):
    """Empty staleness table completes without error and makes no writes."""
    with _patched_run_env(
        [], dry_run_value="false", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_not_called()
        mock_cache.delete.assert_not_called()


def test_run_multiple_near_default_rows_all_deleted(mock_session, mock_app, monkeypatch):
    """All eligible rows are deleted when multiple near-default rows exist."""
    rows = [
        _make_row("org-near-1", JUST_UNDER_ONE_HOUR),
        _make_row("org-near-2", JUST_UNDER_ONE_HOUR),
    ]

    with _patched_run_env(
        rows, dry_run_value="false", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        assert mock_session.delete.call_count == 2
        assert mock_cache.delete.call_count == 2
        mock_cache.delete.assert_any_call("org-near-1")
        mock_cache.delete.assert_any_call("org-near-2")


def test_run_cache_delete_called_per_deleted_row_in_order(mock_session, mock_app, monkeypatch):
    """StalenessCache.delete is called for each deleted row and not for retained rows."""
    row_near = _make_row("org-to-delete", JUST_UNDER_ONE_HOUR)
    row_exact = _make_row("org-to-keep-exact", AT_EXACTLY_ONE_HOUR)
    row_custom = _make_row("org-to-keep-custom", CUSTOM_STALENESS)

    with _patched_run_env(
        [row_near, row_exact, row_custom],
        dry_run_value="false",
        monkeypatch=monkeypatch,
        session=mock_session,
        app=mock_app,
    ) as mock_cache:
        mock_cache.delete.assert_called_once_with("org-to-delete")
        mock_session.delete.assert_called_once_with(row_near)


def test_run_dry_run_retains_multiple_eligible_rows(mock_session, mock_app, monkeypatch):
    """DRY_RUN prevents deletions even when all rows are eligible."""
    rows = [
        _make_row("org-dry-1", JUST_UNDER_ONE_HOUR),
        _make_row("org-dry-2", JUST_UNDER_ONE_HOUR),
        _make_row("org-dry-3", JUST_UNDER_ONE_HOUR),
    ]

    with _patched_run_env(
        rows, dry_run_value="true", monkeypatch=monkeypatch, session=mock_session, app=mock_app
    ) as mock_cache:
        mock_session.delete.assert_not_called()
        mock_cache.delete.assert_not_called()
