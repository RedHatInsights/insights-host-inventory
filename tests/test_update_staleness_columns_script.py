from __future__ import annotations

from typing import Callable
from unittest import mock
from uuid import UUID

import pytest
from connexion import FlaskApp

from app.models import db
from app.models.host import Host
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import get_staleness_timestamps
from update_staleness_columns import run as run_update_staleness_columns


@pytest.mark.parametrize("is_edge_host", [True, False])
def test_update_edge_host_staleness_columns(
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
    is_edge_host: bool,
) -> None:
    staleness_timestamps = get_staleness_timestamps()
    system_profile = {"host_type": "edge"} if is_edge_host else {}

    host = minimal_db_host(
        stale_timestamp=staleness_timestamps["stale"],
        reporter="puptoo",
        system_profile_facts=system_profile,
    )

    created_host = db_create_host(host=host)
    created_host.stale_warning_timestamp = None
    created_host.deletion_timestamp = None
    db.session.commit()

    assert created_host.stale_warning_timestamp is None
    assert created_host.deletion_timestamp is None

    with flask_app.app.app_context():
        run_update_staleness_columns(logger=mock.MagicMock(), session=db.session, application=flask_app)

    updated_host = db_get_host(created_host.id)
    db.session.refresh(updated_host)

    assert updated_host
    assert "stale_warning_timestamp" in updated_host.per_reporter_staleness[host.reporter]
    assert "culled_timestamp" in updated_host.per_reporter_staleness[host.reporter]
    assert updated_host.stale_warning_timestamp is not None
    assert updated_host.deletion_timestamp is not None
