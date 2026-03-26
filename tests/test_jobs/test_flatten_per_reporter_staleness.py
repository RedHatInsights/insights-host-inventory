from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import Mock

from connexion import FlaskApp
from sqlalchemy.orm import attributes as orm_attributes

import jobs.flatten_per_reporter_staleness as flatten_job
from app.models import Host
from app.models import db


def _run_flatten_job(
    flask_app: FlaskApp,
    *,
    dry_run: bool,
    chunk_size: int = 1000,
    logger: Mock | None = None,
) -> None:
    """Invoke ``run()`` with a config mock, matching most job tests."""
    config = Mock(dry_run=dry_run, script_chunk_size=chunk_size)
    flatten_job.run(config=config, logger=logger or Mock(), session=db.session, application=flask_app)


def test_flatten_nested_to_flat_format(flask_app: FlaskApp, db_create_host):
    """Test that nested per_reporter_staleness is correctly flattened to flat format."""

    now_time = datetime.now(UTC)

    # Create host with nested format
    host_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                },
                "yupana": {
                    "last_check_in": (now_time - timedelta(days=2)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=2)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=31)).isoformat(),
                    "check_in_succeeded": True,
                },
            }
        }
    ).id

    db.session.commit()

    _run_flatten_job(flask_app, dry_run=False)

    host = Host.query.filter_by(id=host_id).one()

    # Verify flattened structure: only last_check_in timestamps stored
    assert isinstance(host.per_reporter_staleness["puptoo"], str)
    assert isinstance(host.per_reporter_staleness["yupana"], str)
    assert host.per_reporter_staleness["puptoo"] == (now_time - timedelta(days=1)).isoformat()
    assert host.per_reporter_staleness["yupana"] == (now_time - timedelta(days=2)).isoformat()


def test_flatten_already_flat_format_unchanged(flask_app: FlaskApp, db_create_host):
    """Test that already-flat per_reporter_staleness is not modified."""

    now_time = datetime.now(UTC)

    # Create host with already flat format
    host_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": (now_time - timedelta(days=1)).isoformat(),
                "yupana": (now_time - timedelta(days=2)).isoformat(),
            }
        }
    ).id

    db.session.commit()

    _run_flatten_job(flask_app, dry_run=False)

    host = Host.query.filter_by(id=host_id).one()

    # Verify unchanged - still flat
    assert isinstance(host.per_reporter_staleness["puptoo"], str)
    assert isinstance(host.per_reporter_staleness["yupana"], str)
    assert host.per_reporter_staleness["puptoo"] == (now_time - timedelta(days=1)).isoformat()
    assert host.per_reporter_staleness["yupana"] == (now_time - timedelta(days=2)).isoformat()


def test_flatten_mixed_reporters(flask_app: FlaskApp, db_create_host):
    """Test host with mixed nested and flat reporters (edge case)."""

    now_time = datetime.now(UTC)

    # Create host with mixed format (one nested, one flat - shouldn't happen but test it)
    host_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                },
                "yupana": (now_time - timedelta(days=2)).isoformat(),  # Already flat
            }
        }
    ).id

    db.session.commit()

    _run_flatten_job(flask_app, dry_run=False)

    host = Host.query.filter_by(id=host_id).one()

    # Verify both are now flat
    assert isinstance(host.per_reporter_staleness["puptoo"], str)
    assert isinstance(host.per_reporter_staleness["yupana"], str)
    assert host.per_reporter_staleness["puptoo"] == (now_time - timedelta(days=1)).isoformat()
    assert host.per_reporter_staleness["yupana"] == (now_time - timedelta(days=2)).isoformat()


def test_flatten_empty_per_reporter_staleness(flask_app: FlaskApp, db_create_host):
    """Test that job doesn't fail on hosts with empty per_reporter_staleness."""

    # Create host with a placeholder so Host.__init__ doesn't auto-populate;
    # then clear per_reporter_staleness to {} in the DB (Host treats {} as falsy and
    # would call _update_per_reporter_staleness on create).
    now_time = datetime.now(UTC)
    host = db_create_host(extra_data={"per_reporter_staleness": {"placeholder": now_time.isoformat()}})
    host_id = host.id
    db.session.commit()

    host = Host.query.filter_by(id=host_id).one()
    host.per_reporter_staleness = {}
    orm_attributes.flag_modified(host, "per_reporter_staleness")
    db.session.commit()

    _run_flatten_job(flask_app, dry_run=False)

    host = Host.query.filter_by(id=host_id).one()

    # Job should complete without error and leave empty per_reporter_staleness unchanged
    assert host.per_reporter_staleness == {}


def test_flatten_dry_run_mode(flask_app: FlaskApp, db_create_host):
    """Test that dry-run mode doesn't modify data."""

    now_time = datetime.now(UTC)

    # Create host with nested format
    host_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                },
            }
        }
    ).id

    db.session.commit()

    _run_flatten_job(flask_app, dry_run=True)

    host = Host.query.filter_by(id=host_id).one()

    assert isinstance(host.per_reporter_staleness["puptoo"], dict)
    assert "last_check_in" in host.per_reporter_staleness["puptoo"]
    assert "stale_timestamp" in host.per_reporter_staleness["puptoo"]
    assert "stale_warning_timestamp" in host.per_reporter_staleness["puptoo"]
    assert "culled_timestamp" in host.per_reporter_staleness["puptoo"]
    assert "check_in_succeeded" in host.per_reporter_staleness["puptoo"]


def test_count_hosts_with_nested_format(db_create_host):
    """Test counting hosts with nested format."""

    now_time = datetime.now(UTC)
    org_id = "123456"

    # Create hosts with nested format
    db_create_host(
        extra_data={
            "org_id": org_id,
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    )

    db_create_host(
        extra_data={
            "org_id": org_id,
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    )

    # Create host with flat format (should not be counted)
    db_create_host(
        extra_data={"org_id": org_id, "per_reporter_staleness": {"puptoo": now_time.isoformat()}},
    )

    # Create host in different org (should not be counted)
    db_create_host(
        extra_data={
            "org_id": "999999",
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    )

    db.session.commit()

    count = flatten_job._count_hosts_with_nested_format(db.session, org_id)

    # Should count only the 2 hosts in org_id with nested format
    assert count == 2


def test_get_hosts_with_nested_format(db_create_host):
    """Test querying hosts with nested format."""

    now_time = datetime.now(UTC)
    org_id = "123456"

    # Create hosts with nested format
    host1_id = db_create_host(
        extra_data={
            "org_id": org_id,
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    ).id

    host2_id = db_create_host(
        extra_data={
            "org_id": org_id,
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    ).id

    # Create host with flat format (should not be returned)
    db_create_host(
        extra_data={"org_id": org_id, "per_reporter_staleness": {"puptoo": now_time.isoformat()}},
    )

    db.session.commit()

    hosts = flatten_job._get_hosts_with_nested_format(db.session, org_id, chunk_size=10)

    # Should return only the 2 hosts with nested format
    assert len(hosts) == 2
    host_ids = {h.id for h in hosts}
    assert host_ids == {host1_id, host2_id}


def test_flatten_host_function(db_create_host):
    """Test the _flatten_host_per_reporter_staleness function directly."""

    now_time = datetime.now(UTC)

    # Create host with nested format
    host = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                },
            }
        }
    )

    db.session.commit()

    # Flatten it
    result = flatten_job._flatten_host_per_reporter_staleness(host, Mock(), dry_run=False)

    # Should return True (was modified)
    assert result is True

    # Verify flattened
    assert isinstance(host.per_reporter_staleness["puptoo"], str)
    assert host.per_reporter_staleness["puptoo"] == (now_time - timedelta(days=1)).isoformat()


def test_flatten_host_function_already_flat(db_create_host):
    """Test _flatten_host_per_reporter_staleness with already-flat host."""

    now_time = datetime.now(UTC)

    # Create host with flat format
    host = db_create_host(
        extra_data={"per_reporter_staleness": {"puptoo": (now_time - timedelta(days=1)).isoformat()}}
    )

    db.session.commit()

    # Try to flatten it
    result = flatten_job._flatten_host_per_reporter_staleness(host, Mock(), dry_run=False)

    # Should return False (not modified)
    assert result is False


def test_flatten_host_function_dry_run(db_create_host):
    """Test _flatten_host_per_reporter_staleness in dry-run mode."""

    now_time = datetime.now(UTC)

    # Create host with nested format
    host = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                },
            }
        }
    )

    db.session.commit()

    # Flatten it in dry-run
    result = flatten_job._flatten_host_per_reporter_staleness(host, Mock(), dry_run=True)

    # Should return True (would be modified)
    assert result is True

    # Verify NOT flattened (dry-run)
    assert isinstance(host.per_reporter_staleness["puptoo"], dict)


def test_flatten_multiple_orgs(flask_app: FlaskApp, db_create_host):
    """Test that job processes multiple orgs correctly."""

    now_time = datetime.now(UTC)

    # Create hosts in different orgs
    org1_host_id = db_create_host(
        extra_data={
            "org_id": "111111",
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    ).id

    org2_host_id = db_create_host(
        extra_data={
            "org_id": "222222",
            "per_reporter_staleness": {
                "yupana": {
                    "last_check_in": now_time.isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                    "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    ).id

    db.session.commit()

    _run_flatten_job(flask_app, dry_run=False)

    # Verify both orgs were processed
    org1_host = Host.query.filter_by(id=org1_host_id).one()
    org2_host = Host.query.filter_by(id=org2_host_id).one()

    assert isinstance(org1_host.per_reporter_staleness["puptoo"], str)
    assert isinstance(org2_host.per_reporter_staleness["yupana"], str)


def test_flatten_chunked_processing(flask_app: FlaskApp, db_create_host):
    """Test that job processes hosts in chunks correctly."""

    now_time = datetime.now(UTC)

    # Create 3 hosts with nested format
    host_ids = []
    for _i in range(3):
        host_id = db_create_host(
            extra_data={
                "per_reporter_staleness": {
                    "puptoo": {
                        "last_check_in": now_time.isoformat(),
                        "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                        "stale_warning_timestamp": (now_time + timedelta(days=14)).isoformat(),
                        "culled_timestamp": (now_time + timedelta(days=30)).isoformat(),
                        "check_in_succeeded": True,
                    }
                }
            }
        ).id
        host_ids.append(host_id)

    db.session.commit()

    _run_flatten_job(flask_app, dry_run=False, chunk_size=1)

    # Verify all hosts were processed
    for host_id in host_ids:
        host = Host.query.filter_by(id=host_id).one()
        assert isinstance(host.per_reporter_staleness["puptoo"], str)
