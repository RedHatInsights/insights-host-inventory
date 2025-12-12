# mypy: disallow-untyped-defs

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import pytest
from connexion import FlaskApp

from app.config import Config
from app.logging import get_logger
from app.models import Host
from app.models import db
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from jobs.common import init_db
from jobs.update_rhsm_host_timestamps import run as run_update_rhsm_host_timestamps
from tests.helpers.db_utils import create_rhsm_only_host
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now

logger = get_logger(__name__)


def create_multi_reporter_host(
    stale_timestamp: datetime | None = None,
    stale_warning_timestamp: datetime | None = None,
    deletion_timestamp: datetime | None = None,
) -> Host:
    """Create a host with multiple reporters (not RHSM-only)"""
    # Use the far future timestamp as default if not specified
    stale_ts = stale_timestamp if stale_timestamp is not None else FAR_FUTURE_STALE_TIMESTAMP
    stale_warning_ts = stale_warning_timestamp if stale_warning_timestamp is not None else FAR_FUTURE_STALE_TIMESTAMP
    deletion_ts = deletion_timestamp if deletion_timestamp is not None else FAR_FUTURE_STALE_TIMESTAMP

    host = minimal_db_host(
        insights_id=generate_uuid(),
        reporter="puptoo",
        per_reporter_staleness={
            "puptoo": {
                "last_check_in": now().isoformat(),
                "stale_timestamp": stale_ts.isoformat(),
                "stale_warning_timestamp": stale_warning_ts.isoformat(),
                "culled_timestamp": deletion_ts.isoformat(),
                "check_in_succeeded": True,
            },
            "rhsm-system-profile-bridge": {
                "last_check_in": now().isoformat(),
                "stale_timestamp": stale_ts.isoformat(),
                "stale_warning_timestamp": stale_warning_ts.isoformat(),
                "culled_timestamp": deletion_ts.isoformat(),
                "check_in_succeeded": True,
            },
        },
    )
    # Set timestamps directly as properties after object creation
    host.stale_timestamp = stale_ts
    host.stale_warning_timestamp = stale_warning_ts
    host.deletion_timestamp = deletion_ts
    return host


@pytest.mark.parametrize(
    "incorrect_timestamp_field",
    ["stale_timestamp", "stale_warning_timestamp", "deletion_timestamp"],
)
def test_rhsm_job_updates_rhsm_only_host(
    no_dry_run_config: Config,
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
    incorrect_timestamp_field: str,
) -> None:
    """Test that RHSM-only hosts with incorrect timestamps get updated"""
    # Create an incorrect timestamp (not FAR_FUTURE_STALE_TIMESTAMP)
    incorrect_timestamp = now() + timedelta(days=7)

    # Create host with one incorrect timestamp
    timestamps = {incorrect_timestamp_field: incorrect_timestamp}
    host = create_rhsm_only_host(**timestamps)
    created_host = db_create_host(host=host)
    host_id = created_host.id  # Save the ID before it gets detached

    # Verify the incorrect timestamp was set
    assert getattr(created_host, incorrect_timestamp_field) == incorrect_timestamp

    # Run the update job
    Session = init_db(no_dry_run_config)
    session = Session()

    run_update_rhsm_host_timestamps(no_dry_run_config, logger, session, flask_app)

    # Expire all cached objects in the Flask app's session to ensure we get fresh data
    db.session.expire_all()

    # Retrieve the host and verify all timestamps are now FAR_FUTURE_STALE_TIMESTAMP
    updated_host = db_get_host(host_id)
    assert updated_host is not None
    assert updated_host.stale_timestamp == FAR_FUTURE_STALE_TIMESTAMP
    assert updated_host.stale_warning_timestamp == FAR_FUTURE_STALE_TIMESTAMP
    assert updated_host.deletion_timestamp == FAR_FUTURE_STALE_TIMESTAMP

    # Verify per_reporter_staleness was also updated
    assert len(updated_host.per_reporter_staleness) == 1
    assert "rhsm-system-profile-bridge" in updated_host.per_reporter_staleness
    rhsm_staleness = updated_host.per_reporter_staleness["rhsm-system-profile-bridge"]
    assert rhsm_staleness["stale_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP.isoformat()
    assert rhsm_staleness["stale_warning_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP.isoformat()
    assert rhsm_staleness["culled_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP.isoformat()


def test_rhsm_job_does_not_update_non_rhsm_only_host(
    no_dry_run_config: Config,
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
) -> None:
    """Test that non-RHSM-only hosts are not updated even if they have incorrect timestamps"""
    # Create timestamps that are not FAR_FUTURE_STALE_TIMESTAMP
    incorrect_stale_timestamp = now() + timedelta(days=1)
    incorrect_stale_warning_timestamp = now() + timedelta(days=7)
    incorrect_deletion_timestamp = now() + timedelta(days=14)

    # Create a host with multiple reporters (not RHSM-only)
    host = create_multi_reporter_host(
        stale_timestamp=incorrect_stale_timestamp,
        stale_warning_timestamp=incorrect_stale_warning_timestamp,
        deletion_timestamp=incorrect_deletion_timestamp,
    )
    created_host = db_create_host(host=host)

    # Verify the timestamps were set
    assert created_host.stale_timestamp == incorrect_stale_timestamp
    assert created_host.stale_warning_timestamp == incorrect_stale_warning_timestamp
    assert created_host.deletion_timestamp == incorrect_deletion_timestamp

    # Run the update job
    Session = init_db(no_dry_run_config)
    session = Session()

    run_update_rhsm_host_timestamps(no_dry_run_config, logger, session, flask_app)

    # Expire all cached objects in the Flask app's session to ensure we get fresh data
    db.session.expire_all()

    # Retrieve the host and verify timestamps were NOT changed
    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host is not None
    assert retrieved_host.stale_timestamp == incorrect_stale_timestamp
    assert retrieved_host.stale_warning_timestamp == incorrect_stale_warning_timestamp
    assert retrieved_host.deletion_timestamp == incorrect_deletion_timestamp

    # Verify per_reporter_staleness was also NOT updated
    assert len(retrieved_host.per_reporter_staleness) == 2
    assert "puptoo" in retrieved_host.per_reporter_staleness
    assert "rhsm-system-profile-bridge" in retrieved_host.per_reporter_staleness
    for prs in retrieved_host.per_reporter_staleness.values():
        assert prs["stale_timestamp"] == incorrect_stale_timestamp.isoformat()
        assert prs["stale_warning_timestamp"] == incorrect_stale_warning_timestamp.isoformat()
        assert prs["culled_timestamp"] == incorrect_deletion_timestamp.isoformat()


def test_rhsm_job_does_not_update_hosts_in_dry_run_mode(
    inventory_config: Config,
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
) -> None:
    """Test that running the job in dry-run mode does not update any hosts"""
    # Set dry_run mode
    inventory_config.dry_run = True

    # Create timestamps that are not FAR_FUTURE_STALE_TIMESTAMP
    incorrect_stale_timestamp = now() + timedelta(days=1)
    incorrect_stale_warning_timestamp = now() + timedelta(days=7)
    incorrect_deletion_timestamp = now() + timedelta(days=14)

    # Create RHSM-only host with incorrect timestamp
    host = create_rhsm_only_host(
        stale_timestamp=incorrect_stale_timestamp,
        stale_warning_timestamp=incorrect_stale_warning_timestamp,
        deletion_timestamp=incorrect_deletion_timestamp,
    )
    created_host = db_create_host(host=host)

    # Verify the timestamps were set
    assert created_host.stale_timestamp == incorrect_stale_timestamp
    assert created_host.stale_warning_timestamp == incorrect_stale_warning_timestamp
    assert created_host.deletion_timestamp == incorrect_deletion_timestamp

    # Run the update job in dry-run mode
    Session = init_db(inventory_config)
    session = Session()

    run_update_rhsm_host_timestamps(inventory_config, logger, session, flask_app)

    # Expire all cached objects in the Flask app's session to ensure we get fresh data
    db.session.expire_all()

    # Retrieve the host and verify timestamp was NOT changed
    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host is not None
    assert retrieved_host.stale_timestamp == incorrect_stale_timestamp
    assert retrieved_host.stale_warning_timestamp == incorrect_stale_warning_timestamp
    assert retrieved_host.deletion_timestamp == incorrect_deletion_timestamp

    # Verify per_reporter_staleness was also NOT updated
    assert len(retrieved_host.per_reporter_staleness) == 1
    assert "rhsm-system-profile-bridge" in retrieved_host.per_reporter_staleness
    rhsm_staleness = retrieved_host.per_reporter_staleness["rhsm-system-profile-bridge"]
    assert rhsm_staleness["stale_timestamp"] == incorrect_stale_timestamp.isoformat()
    assert rhsm_staleness["stale_warning_timestamp"] == incorrect_stale_warning_timestamp.isoformat()
    assert rhsm_staleness["culled_timestamp"] == incorrect_deletion_timestamp.isoformat()
