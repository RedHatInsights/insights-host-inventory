from unittest import mock

import pytest
from connexion import FlaskApp
from jobs.canonical_facts_migration import run as canonical_facts_migration_run
from sqlalchemy import text

from app.logging import get_logger
from app.models import db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import generate_uuid

logger = get_logger(__name__)


@pytest.mark.canonical_facts_migration
def test_canonical_facts_migration_runs_successfully(
    flask_app: FlaskApp,
    db_create_host,
    db_get_host,
):
    """
    Test that the canonical facts migration job correctly updates NULL canonical facts columns
    from the canonical_facts JSONB column.
    """
    # Create a host with canonical facts data
    insights_id = generate_uuid()
    bios_uuid = generate_uuid()

    canonical_facts = {
        "insights_id": insights_id,
        "fqdn": "test-host.example.com",
        "bios_uuid": bios_uuid,
        "provider_type": "aws",
    }

    host_data = minimal_db_host(canonical_facts=canonical_facts)
    created_host = db_create_host(host=host_data)

    # Set bios_uuid to NULL to create a migration scenario
    # (insights_id has a NOT NULL constraint so we can't set it to NULL)
    update_sql = text("""
        UPDATE hbi.hosts
        SET bios_uuid = NULL
        WHERE id = :host_id
    """)
    db.session.execute(update_sql, {"host_id": created_host.id})
    db.session.commit()

    # Verify setup: bios_uuid is NULL but canonical_facts contains data
    host_before = db_get_host(created_host.id)
    assert host_before.bios_uuid is None
    assert host_before.canonical_facts["bios_uuid"] == bios_uuid

    # Run the migration job
    logger_mock = mock.Mock()

    with mock.patch.dict("os.environ", {"CANONICAL_FACTS_MIGRATION_BATCH_SIZE": "1"}):
        with flask_app.app.app_context():
            canonical_facts_migration_run(logger_mock, db.session, flask_app)

    # Verify the job completed successfully and found hosts to update
    log_messages = [str(call) for call in logger_mock.info.call_args_list]
    assert any("Successfully finished updating canonical facts" in msg for msg in log_messages)
    assert any("Total rows updated: 1" in msg for msg in log_messages)
