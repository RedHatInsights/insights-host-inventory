from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import Mock

from connexion import FlaskApp

from app.models import Host
from app.models import db
from jobs.backfill_per_reporter_culled_timestamps import run


def test_backfill_missing_culled_timestamps_happy_path(
    flask_app: FlaskApp,
    db_create_host,
):
    """Test that missing culled_timestamps are backfilled correctly."""

    now_time = datetime.now(UTC)
    puptoo_culled_timestamp = (now_time + timedelta(days=30)).isoformat()
    host1_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=7)).isoformat(),
                    "check_in_succeeded": True,
                    # Missing culled_timestamp
                },
                "yupana": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=7)).isoformat(),
                    "check_in_succeeded": True,
                    # Missing culled_timestamp
                },
            }
        }
    ).id

    host2_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=7)).isoformat(),
                    "culled_timestamp": puptoo_culled_timestamp,  # Has culled_timestamp
                    "check_in_succeeded": True,
                },
                "yupana": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=7)).isoformat(),
                    "check_in_succeeded": True,
                    # Missing culled_timestamp
                },
            }
        }
    ).id

    # all reporters have culled_timestamp (should be skipped)
    host3_id = db_create_host(
        extra_data={
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (now_time - timedelta(days=1)).isoformat(),
                    "stale_timestamp": (now_time + timedelta(days=1)).isoformat(),
                    "stale_warning_timestamp": (now_time + timedelta(days=7)).isoformat(),
                    "culled_timestamp": puptoo_culled_timestamp,
                    "check_in_succeeded": True,
                }
            }
        }
    ).id

    db.session.commit()

    run(
        logger=Mock(),
        session=db.session,
        application=flask_app,
        config=Mock(dry_run=False, script_chunk_size=1000),
    )

    host1 = Host.query.filter_by(id=host1_id).one()
    host2 = Host.query.filter_by(id=host2_id).one()
    host3 = Host.query.filter_by(id=host3_id).one()

    # Check that culled_timestamp was added to reporters that were missing it
    for reporter in ["puptoo", "yupana"]:
        assert host1.per_reporter_staleness[reporter]["culled_timestamp"] is not None

    # Check host2: puptoo should still have its original culled_timestamp, yupana should get one
    assert host2.per_reporter_staleness["puptoo"]["culled_timestamp"] == puptoo_culled_timestamp
    assert host2.per_reporter_staleness["yupana"]["culled_timestamp"] is not None

    # Check host3: should be unchanged (all reporters already had culled_timestamp)
    assert host3.per_reporter_staleness["puptoo"]["culled_timestamp"] == puptoo_culled_timestamp
