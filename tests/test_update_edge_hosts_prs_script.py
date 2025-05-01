from unittest import mock

from app.models import db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import get_staleness_timestamps
from update_edge_hosts_prs import run as run_update_edge_hosts_prs


def test_update_edge_host_prs(flask_app, db_create_host, db_get_host):
    staleness_timestamps = get_staleness_timestamps()

    host = minimal_db_host(
        stale_timestamp=staleness_timestamps["stale"],
        reporter="puptoo",
        system_profile_facts={"host_type": "edge"},
    )

    created_host = db_create_host(host=host)

    with flask_app.app.app_context():
        assert "culled_timestamp" not in created_host.per_reporter_staleness[host.reporter]
        run_update_edge_hosts_prs(logger=mock.MagicMock(), session=db.session, application=flask_app)
        updated_host = db_get_host(created_host.id)
        assert "culled_timestamp" in updated_host.per_reporter_staleness[host.reporter]


def test_do_not_update_conventional_host_prs(flask_app, db_create_host, db_get_host):
    staleness_timestamps = get_staleness_timestamps()

    host = minimal_db_host(
        stale_timestamp=staleness_timestamps["stale"],
        reporter="puptoo",
    )

    created_host = db_create_host(host=host)

    with flask_app.app.app_context():
        assert "culled_timestamp" not in created_host.per_reporter_staleness[host.reporter]
        run_update_edge_hosts_prs(logger=mock.MagicMock(), session=db.session, application=flask_app)
        updated_host = db_get_host(created_host.id)
        assert "culled_timestamp" not in updated_host.per_reporter_staleness[host.reporter]
