import logging

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Staleness
from app.models import db
from jobs.clean_custom_staleness import _build_equivalence_filter
from jobs.clean_custom_staleness import run
from lib.staleness import DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS

_logger = logging.getLogger("test_clean_custom_staleness")

# Tolerance is exclusive: < 3600 s is equivalent, >= 3600 s is not.
TOLERANCE = DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS  # 3600

# A value just inside the equivalence window for all three fields.
NEAR_DEFAULT_STALE = CONVENTIONAL_TIME_TO_STALE_SECONDS + (TOLERANCE - 1)
NEAR_DEFAULT_WARNING = CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - (TOLERANCE - 1)
NEAR_DEFAULT_DELETE = CONVENTIONAL_TIME_TO_DELETE_SECONDS + (TOLERANCE - 1)

# A value exactly at the boundary — NOT equivalent.
AT_BOUNDARY_STALE = CONVENTIONAL_TIME_TO_STALE_SECONDS + TOLERANCE
AT_BOUNDARY_WARNING = CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + TOLERANCE
AT_BOUNDARY_DELETE = CONVENTIONAL_TIME_TO_DELETE_SECONDS + TOLERANCE

# Clearly different values
TRULY_CUSTOM_STALE = 200000
TRULY_CUSTOM_WARNING = 700000
TRULY_CUSTOM_DELETE = 3000000

ORG_NEAR_DEFAULT = "clean-staleness-near-default-org"
ORG_TRULY_CUSTOM = "clean-staleness-truly-custom-org"
ORG_EXACT_DEFAULT = "clean-staleness-exact-default-org"
ORG_AT_BOUNDARY = "clean-staleness-at-boundary-org"


def _get_staleness_row(org_id: str):
    return Staleness.query.filter(Staleness.org_id == org_id).one_or_none()


def _create_staleness_row(org_id: str, stale: int, warning: int, delete: int) -> Staleness:
    row = Staleness(
        org_id=org_id,
        conventional_time_to_stale=stale,
        conventional_time_to_stale_warning=warning,
        conventional_time_to_delete=delete,
    )
    db.session.add(row)
    db.session.commit()
    return row


# ---------------------------------------------------------------------------
# Unit tests for _build_equivalence_filter
# ---------------------------------------------------------------------------


def test_build_equivalence_filter_returns_three_conditions():
    conditions = _build_equivalence_filter()
    assert len(conditions) == 3


# ---------------------------------------------------------------------------
# Integration tests for run()
# ---------------------------------------------------------------------------


def test_run_dry_run_does_not_delete(flask_app, monkeypatch):
    """Rows are not deleted when DRY_RUN=true."""
    monkeypatch.setenv("DRY_RUN", "true")

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_NEAR_DEFAULT,
            NEAR_DEFAULT_STALE,
            NEAR_DEFAULT_WARNING,
            NEAR_DEFAULT_DELETE,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 0
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_NEAR_DEFAULT) is not None


def test_run_deletes_near_default_row(flask_app, monkeypatch):
    """A row whose all fields are within tolerance of defaults is deleted."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_NEAR_DEFAULT,
            NEAR_DEFAULT_STALE,
            NEAR_DEFAULT_WARNING,
            NEAR_DEFAULT_DELETE,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 1
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_NEAR_DEFAULT) is None


def test_run_deletes_exact_default_row(flask_app, monkeypatch):
    """A row with values exactly equal to system defaults is deleted."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_EXACT_DEFAULT,
            CONVENTIONAL_TIME_TO_STALE_SECONDS,
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 1
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_EXACT_DEFAULT) is None


def test_run_preserves_truly_custom_row(flask_app, monkeypatch):
    """A row with values clearly outside the tolerance window is NOT deleted."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_TRULY_CUSTOM,
            TRULY_CUSTOM_STALE,
            TRULY_CUSTOM_WARNING,
            TRULY_CUSTOM_DELETE,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 0
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_TRULY_CUSTOM) is not None


def test_run_preserves_row_at_boundary(flask_app, monkeypatch):
    """A row where any field differs by exactly TOLERANCE seconds is NOT deleted."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_AT_BOUNDARY,
            AT_BOUNDARY_STALE,
            AT_BOUNDARY_WARNING,
            AT_BOUNDARY_DELETE,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 0
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_AT_BOUNDARY) is not None


def test_run_deletes_only_equivalent_rows(flask_app, monkeypatch):
    """Only the near-default row is deleted; the truly custom row is preserved."""
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_NEAR_DEFAULT,
            NEAR_DEFAULT_STALE,
            NEAR_DEFAULT_WARNING,
            NEAR_DEFAULT_DELETE,
        )
        _create_staleness_row(
            ORG_TRULY_CUSTOM,
            TRULY_CUSTOM_STALE,
            TRULY_CUSTOM_WARNING,
            TRULY_CUSTOM_DELETE,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 1
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_NEAR_DEFAULT) is None
        assert _get_staleness_row(ORG_TRULY_CUSTOM) is not None


def test_run_noop_when_no_staleness_rows(flask_app, monkeypatch):
    """run() returns 0 and does not raise when the staleness table is empty."""
    monkeypatch.setenv("DRY_RUN", "false")

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 0


def test_run_dry_run_defaults_to_true_when_unset(flask_app, monkeypatch):
    """DRY_RUN should default to true when the env var is not set."""
    monkeypatch.delenv("DRY_RUN", raising=False)

    with flask_app.app.app_context():
        _create_staleness_row(
            ORG_NEAR_DEFAULT,
            NEAR_DEFAULT_STALE,
            NEAR_DEFAULT_WARNING,
            NEAR_DEFAULT_DELETE,
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 0
    with flask_app.app.app_context():
        assert _get_staleness_row(ORG_NEAR_DEFAULT) is not None


def test_run_one_field_outside_tolerance_preserves_row(flask_app, monkeypatch):
    """If even one conventional field is outside tolerance the row must be kept."""
    monkeypatch.setenv("DRY_RUN", "false")

    org = "clean-staleness-one-field-outside"
    with flask_app.app.app_context():
        _create_staleness_row(
            org,
            CONVENTIONAL_TIME_TO_STALE_SECONDS + 100,  # within tolerance
            CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + TOLERANCE,  # at boundary → NOT equivalent
            CONVENTIONAL_TIME_TO_DELETE_SECONDS + 100,  # within tolerance
        )

    session = db.session
    deleted = run(_logger, session, flask_app)

    assert deleted == 0
    with flask_app.app.app_context():
        assert _get_staleness_row(org) is not None
