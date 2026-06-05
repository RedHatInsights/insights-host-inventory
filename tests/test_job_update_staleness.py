import logging
from unittest.mock import patch

import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Staleness
from app.models import db
from jobs.update_staleness import _merge_with_defaults
from jobs.update_staleness import _read_env_staleness_values
from jobs.update_staleness import run

_logger = logging.getLogger("test_update_staleness")

CUSTOM_ORG_ID = "update-staleness-test-org"
CUSTOM_STALE = 200000
CUSTOM_WARNING = 700000
CUSTOM_DELETE = 3000000


# -- _read_env_staleness_values -----------------------------------------------


def test_read_env_no_vars_set():
    with patch.dict("os.environ", {}, clear=True):
        assert _read_env_staleness_values(_logger) == {}


def test_read_env_all_vars_set():
    env = {
        "CONVENTIONAL_TIME_TO_STALE": "100",
        "CONVENTIONAL_TIME_TO_STALE_WARNING": "200",
        "CONVENTIONAL_TIME_TO_DELETE": "300",
    }
    with patch.dict("os.environ", env, clear=True):
        result = _read_env_staleness_values(_logger)
    assert result == {
        "conventional_time_to_stale": 100,
        "conventional_time_to_stale_warning": 200,
        "conventional_time_to_delete": 300,
    }


def test_read_env_partial_vars():
    env = {"CONVENTIONAL_TIME_TO_DELETE": "999"}
    with patch.dict("os.environ", env, clear=True):
        result = _read_env_staleness_values(_logger)
    assert result == {"conventional_time_to_delete": 999}


def test_read_env_non_integer_exits():
    env = {"CONVENTIONAL_TIME_TO_STALE": "abc"}
    with patch.dict("os.environ", env, clear=True), pytest.raises(SystemExit) as exc_info:
        _read_env_staleness_values(_logger)
    assert exc_info.value.code == 1


def test_read_env_empty_string_exits():
    env = {"CONVENTIONAL_TIME_TO_DELETE": ""}
    with patch.dict("os.environ", env, clear=True), pytest.raises(SystemExit) as exc_info:
        _read_env_staleness_values(_logger)
    assert exc_info.value.code == 1


# -- _merge_with_defaults -----------------------------------------------------


def test_merge_no_existing_row_uses_system_defaults():
    explicit = {"conventional_time_to_stale": 200000}
    merged = _merge_with_defaults(explicit, None)
    assert merged["conventional_time_to_stale"] == 200000
    assert merged["conventional_time_to_stale_warning"] == CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
    assert merged["conventional_time_to_delete"] == CONVENTIONAL_TIME_TO_DELETE_SECONDS


def test_merge_with_existing_row(flask_app):
    with flask_app.app.app_context():
        row = Staleness(
            org_id="merge-test-org",
            conventional_time_to_stale=111,
            conventional_time_to_stale_warning=222,
            conventional_time_to_delete=333,
        )
        explicit = {"conventional_time_to_delete": 999}
        merged = _merge_with_defaults(explicit, row)
    assert merged["conventional_time_to_stale"] == 111
    assert merged["conventional_time_to_stale_warning"] == 222
    assert merged["conventional_time_to_delete"] == 999


def test_merge_all_explicit_ignores_defaults():
    explicit = {
        "conventional_time_to_stale": 1,
        "conventional_time_to_stale_warning": 2,
        "conventional_time_to_delete": 3,
    }
    merged = _merge_with_defaults(explicit, None)
    assert merged == explicit


# -- run() integration tests ---------------------------------------------------


@pytest.fixture()
def _staleness_env(monkeypatch):
    """Set the minimal env for a valid run."""
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", str(CUSTOM_STALE))
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE_WARNING", str(CUSTOM_WARNING))
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_DELETE", str(CUSTOM_DELETE))
    monkeypatch.setenv("DRY_RUN", "false")


def _get_staleness_row(org_id):
    return Staleness.query.filter(Staleness.org_id == org_id).one_or_none()


def test_run_creates_new_row(flask_app, _staleness_env):
    with flask_app.app.app_context():
        assert _get_staleness_row(CUSTOM_ORG_ID) is None

    session = db.session

    with patch("jobs.update_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        row = _get_staleness_row(CUSTOM_ORG_ID)
        assert row is not None
        assert row.conventional_time_to_stale == CUSTOM_STALE
        assert row.conventional_time_to_stale_warning == CUSTOM_WARNING
        assert row.conventional_time_to_delete == CUSTOM_DELETE
        mock_cache.delete.assert_called_once_with(CUSTOM_ORG_ID)


def test_run_updates_existing_row(flask_app, _staleness_env, monkeypatch):
    with flask_app.app.app_context():
        existing = Staleness(
            org_id=CUSTOM_ORG_ID,
            conventional_time_to_stale=1,
            conventional_time_to_stale_warning=2,
            conventional_time_to_delete=3,
        )
        db.session.add(existing)
        db.session.commit()

    new_stale = 150000
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", str(new_stale))

    session = db.session

    with patch("jobs.update_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        row = _get_staleness_row(CUSTOM_ORG_ID)
        assert row is not None
        assert row.conventional_time_to_stale == new_stale
        assert row.conventional_time_to_stale_warning == CUSTOM_WARNING
        assert row.conventional_time_to_delete == CUSTOM_DELETE
        mock_cache.delete.assert_called_once_with(CUSTOM_ORG_ID)


def test_run_partial_create_uses_system_defaults(flask_app, monkeypatch):
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", str(CUSTOM_STALE))
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_STALE_WARNING", raising=False)
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_DELETE", raising=False)

    session = db.session

    with patch("jobs.update_staleness.StalenessCache"):
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        row = _get_staleness_row(CUSTOM_ORG_ID)
        assert row is not None
        assert row.conventional_time_to_stale == CUSTOM_STALE
        assert row.conventional_time_to_stale_warning == CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
        assert row.conventional_time_to_delete == CONVENTIONAL_TIME_TO_DELETE_SECONDS


def test_run_partial_update_preserves_existing(flask_app, monkeypatch):
    with flask_app.app.app_context():
        existing = Staleness(
            org_id=CUSTOM_ORG_ID,
            conventional_time_to_stale=CUSTOM_STALE,
            conventional_time_to_stale_warning=CUSTOM_WARNING,
            conventional_time_to_delete=CUSTOM_DELETE,
        )
        db.session.add(existing)
        db.session.commit()

    new_delete = 5000000
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_DELETE", str(new_delete))
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_STALE", raising=False)
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_STALE_WARNING", raising=False)

    session = db.session

    with patch("jobs.update_staleness.StalenessCache"):
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        row = _get_staleness_row(CUSTOM_ORG_ID)
        assert row is not None
        assert row.conventional_time_to_stale == CUSTOM_STALE
        assert row.conventional_time_to_stale_warning == CUSTOM_WARNING
        assert row.conventional_time_to_delete == new_delete


def test_run_dry_run_does_not_write(flask_app, monkeypatch):
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", str(CUSTOM_STALE))
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE_WARNING", str(CUSTOM_WARNING))
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_DELETE", str(CUSTOM_DELETE))
    monkeypatch.setenv("DRY_RUN", "true")

    session = db.session

    with patch("jobs.update_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(CUSTOM_ORG_ID) is None
        mock_cache.delete.assert_not_called()


def test_run_missing_org_id_exits(flask_app, monkeypatch):
    monkeypatch.setenv("STALENESS_ORG_ID", "")
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", "100")

    session = db.session

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1


def test_run_no_staleness_env_vars_exits(flask_app, monkeypatch):
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_STALE", raising=False)
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_STALE_WARNING", raising=False)
    monkeypatch.delenv("CONVENTIONAL_TIME_TO_DELETE", raising=False)

    session = db.session

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1


def test_run_invalid_values_exits(flask_app, monkeypatch):
    """stale >= warning should fail schema validation."""
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", "500000")
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE_WARNING", "100")
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_DELETE", "3000000")
    monkeypatch.setenv("DRY_RUN", "false")

    session = db.session

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1

    with flask_app.app.app_context():
        assert _get_staleness_row(CUSTOM_ORG_ID) is None


def test_run_dry_run_defaults_to_true_when_unset(flask_app, monkeypatch):
    """DRY_RUN should default to true when the env var is not set."""
    monkeypatch.setenv("STALENESS_ORG_ID", CUSTOM_ORG_ID)
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE", str(CUSTOM_STALE))
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_STALE_WARNING", str(CUSTOM_WARNING))
    monkeypatch.setenv("CONVENTIONAL_TIME_TO_DELETE", str(CUSTOM_DELETE))
    monkeypatch.delenv("DRY_RUN", raising=False)

    session = db.session

    with patch("jobs.update_staleness.StalenessCache") as mock_cache:
        run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _get_staleness_row(CUSTOM_ORG_ID) is None
        mock_cache.delete.assert_not_called()
