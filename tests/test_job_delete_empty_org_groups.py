import logging

import pytest

from app.models import Group
from app.models import db
from jobs.delete_empty_org_groups import _env_flag
from jobs.delete_empty_org_groups import _format_group_ids_for_log
from jobs.delete_empty_org_groups import _parse_org_ids
from jobs.delete_empty_org_groups import run
from tests.helpers.test_utils import SYSTEM_IDENTITY

_logger = logging.getLogger("test_delete_empty_org_groups")

EMPTY_ORG_A = "delete-empty-groups-org-a"
EMPTY_ORG_B = "delete-empty-groups-org-b"
HOSTED_ORG = "delete-empty-groups-org-with-hosts"


def _identity_for(org_id: str) -> dict:
    return {
        **SYSTEM_IDENTITY,
        "org_id": org_id,
        "account_number": org_id[:10],
    }


def _group_count(org_id: str) -> int:
    return Group.query.filter(Group.org_id == org_id).count()


# -- _parse_org_ids -----------------------------------------------------------


def test_parse_org_ids_basic():
    assert _parse_org_ids("a,b,c") == ["a", "b", "c"]


def test_parse_org_ids_strips_whitespace_and_dedupes():
    assert _parse_org_ids(" a , b , a ,  ,c ") == ["a", "b", "c"]


def test_parse_org_ids_empty_string():
    assert _parse_org_ids("") == []


# -- _env_flag / _format_group_ids_for_log ------------------------------------


def test_env_flag_defaults_true(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)
    assert _env_flag("SOME_FLAG", default=True) is True


def test_env_flag_defaults_false(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)
    assert _env_flag("SOME_FLAG", default=False) is False


def test_env_flag_reads_true_false(monkeypatch):
    monkeypatch.setenv("SOME_FLAG", "false")
    assert _env_flag("SOME_FLAG", default=True) is False
    monkeypatch.setenv("SOME_FLAG", "TRUE")
    assert _env_flag("SOME_FLAG", default=False) is True


def test_format_group_ids_no_truncation():
    ids = [f"id-{i}" for i in range(5)]
    assert _format_group_ids_for_log(ids) == ids


def test_format_group_ids_truncates():
    ids = [f"id-{i}" for i in range(12)]
    result = _format_group_ids_for_log(ids)
    assert result[:10] == ids[:10]
    assert result[-1] == "...and 2 more"
    assert len(result) == 11


# -- run() integration tests --------------------------------------------------


@pytest.fixture()
def _job_env(monkeypatch):
    monkeypatch.setenv("ORG_IDS", f"{EMPTY_ORG_A},{EMPTY_ORG_B}")
    monkeypatch.setenv("DRY_RUN", "false")


def test_run_requires_org_ids(flask_app, monkeypatch):
    monkeypatch.setenv("ORG_IDS", "")
    monkeypatch.setenv("DRY_RUN", "false")
    session = db.session

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1


def test_run_exits_when_org_has_hosts(flask_app, monkeypatch, db_create_group, db_create_host):
    monkeypatch.setenv("ORG_IDS", f"{EMPTY_ORG_A},{HOSTED_ORG}")
    monkeypatch.setenv("DRY_RUN", "false")

    with flask_app.app.app_context():
        db_create_group("Ungrouped Hosts", identity=_identity_for(EMPTY_ORG_A), ungrouped=True)
        db_create_group("Ungrouped Hosts", identity=_identity_for(HOSTED_ORG), ungrouped=True)
        db_create_host(identity=_identity_for(HOSTED_ORG), extra_data={"org_id": HOSTED_ORG})

        assert _group_count(EMPTY_ORG_A) == 1
        assert _group_count(HOSTED_ORG) == 1

    session = db.session
    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1

    # No groups should have been deleted when any org has hosts.
    with flask_app.app.app_context():
        assert _group_count(EMPTY_ORG_A) == 1
        assert _group_count(HOSTED_ORG) == 1


def test_run_deletes_groups_for_empty_orgs(flask_app, _job_env, db_create_group):
    with flask_app.app.app_context():
        db_create_group("Ungrouped Hosts", identity=_identity_for(EMPTY_ORG_A), ungrouped=True)
        db_create_group("Extra Group", identity=_identity_for(EMPTY_ORG_A))
        db_create_group("Ungrouped Hosts", identity=_identity_for(EMPTY_ORG_B), ungrouped=True)
        # Unrelated org should be left alone.
        other_org = "delete-empty-groups-other"
        db_create_group("Keep Me", identity=_identity_for(other_org))

        assert _group_count(EMPTY_ORG_A) == 2
        assert _group_count(EMPTY_ORG_B) == 1
        assert _group_count(other_org) == 1

    session = db.session
    run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _group_count(EMPTY_ORG_A) == 0
        assert _group_count(EMPTY_ORG_B) == 0
        assert _group_count(other_org) == 1


def test_run_dry_run_does_not_delete(flask_app, monkeypatch, db_create_group):
    monkeypatch.setenv("ORG_IDS", EMPTY_ORG_A)
    monkeypatch.setenv("DRY_RUN", "true")

    with flask_app.app.app_context():
        db_create_group("Ungrouped Hosts", identity=_identity_for(EMPTY_ORG_A), ungrouped=True)
        assert _group_count(EMPTY_ORG_A) == 1

    session = db.session
    run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _group_count(EMPTY_ORG_A) == 1


def test_run_dry_run_defaults_to_true(flask_app, monkeypatch, db_create_group):
    monkeypatch.setenv("ORG_IDS", EMPTY_ORG_A)
    monkeypatch.delenv("DRY_RUN", raising=False)

    with flask_app.app.app_context():
        db_create_group("Ungrouped Hosts", identity=_identity_for(EMPTY_ORG_A), ungrouped=True)

    session = db.session
    run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _group_count(EMPTY_ORG_A) == 1


def test_run_noop_when_no_groups(flask_app, monkeypatch):
    monkeypatch.setenv("ORG_IDS", EMPTY_ORG_A)
    monkeypatch.setenv("DRY_RUN", "false")

    session = db.session
    run(_logger, session, flask_app)

    with flask_app.app.app_context():
        assert _group_count(EMPTY_ORG_A) == 0


def test_run_with_whitespace_only_org_ids_exits(flask_app, monkeypatch):
    monkeypatch.setenv("ORG_IDS", "  ,  , ")
    monkeypatch.setenv("DRY_RUN", "false")
    session = db.session

    with pytest.raises(SystemExit) as exc_info:
        run(_logger, session, flask_app)
    assert exc_info.value.code == 1
