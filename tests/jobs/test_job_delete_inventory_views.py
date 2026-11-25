import logging

import pytest

from app.models import InventoryView
from app.models import UserViewPreference
from app.models import db
from jobs.delete_inventory_views import run

_logger = logging.getLogger("test_delete_inventory_views")


def _view_count(view_id) -> int:
    return InventoryView.query.filter(InventoryView.id == view_id).count()


# -- run() integration tests --------------------------------------------------


def test_run_requires_view_ids(flask_app, monkeypatch):
    monkeypatch.setenv("VIEW_IDS", "")
    monkeypatch.setenv("DRY_RUN", "false")

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, db.session, flask_app)
    assert exc_info.value.code == 1


def test_run_exits_when_no_valid_uuids(flask_app, monkeypatch):
    monkeypatch.setenv("VIEW_IDS", "not-a-uuid, also-bad")
    monkeypatch.setenv("DRY_RUN", "false")

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, db.session, flask_app)
    assert exc_info.value.code == 1


def test_run_deletes_requested_views(flask_app, monkeypatch, db_create_view):
    with flask_app.app.app_context():
        target_a = db_create_view(name="Target A")
        target_b = db_create_view(name="Target B")
        keep = db_create_view(name="Keep Me")
        target_a_id, target_b_id, keep_id = target_a.id, target_b.id, keep.id

    monkeypatch.setenv("VIEW_IDS", f"{target_a_id},{target_b_id}")
    monkeypatch.setenv("DRY_RUN", "false")

    run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _view_count(target_a_id) == 0
        assert _view_count(target_b_id) == 0
        assert _view_count(keep_id) == 1


def test_run_cascades_to_user_view_preferences(flask_app, monkeypatch, db_create_view, db_create_user_view_preference):
    with flask_app.app.app_context():
        view = db_create_view(name="Defaulted View", org_id="cascade-org")
        view_id = view.id
        db_create_user_view_preference(org_id="cascade-org", user_id="user-1", default_view_id=view_id)
        assert UserViewPreference.query.filter(UserViewPreference.default_view_id == view_id).count() == 1

    monkeypatch.setenv("VIEW_IDS", str(view_id))
    monkeypatch.setenv("DRY_RUN", "false")

    run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _view_count(view_id) == 0
        assert UserViewPreference.query.filter(UserViewPreference.default_view_id == view_id).count() == 0


def test_run_dry_run_does_not_delete(flask_app, monkeypatch, db_create_view):
    with flask_app.app.app_context():
        view = db_create_view(name="Target")
        view_id = view.id

    monkeypatch.setenv("VIEW_IDS", str(view_id))
    monkeypatch.setenv("DRY_RUN", "true")

    run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _view_count(view_id) == 1


def test_run_dry_run_defaults_to_true(flask_app, monkeypatch, db_create_view):
    with flask_app.app.app_context():
        view = db_create_view(name="Target")
        view_id = view.id

    monkeypatch.setenv("VIEW_IDS", str(view_id))
    monkeypatch.delenv("DRY_RUN", raising=False)

    run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _view_count(view_id) == 1


def test_run_skips_missing_ids_and_deletes_existing(flask_app, monkeypatch, db_create_view):
    import uuid

    missing_id = uuid.uuid4()
    with flask_app.app.app_context():
        view = db_create_view(name="Target")
        view_id = view.id

    monkeypatch.setenv("VIEW_IDS", f"{view_id},{missing_id}")
    monkeypatch.setenv("DRY_RUN", "false")

    run(_logger, db.session, flask_app)

    with flask_app.app.app_context():
        assert _view_count(view_id) == 0


def test_run_noop_when_none_exist(flask_app, monkeypatch):
    import uuid

    monkeypatch.setenv("VIEW_IDS", str(uuid.uuid4()))
    monkeypatch.setenv("DRY_RUN", "false")

    # Should not raise; simply logs that there is nothing to delete.
    run(_logger, db.session, flask_app)
