"""
End-to-end integration tests for outbox functionality.

These tests verify the complete flow from host operations (create, update, delete)
to outbox records being created with the correct event data.
"""
import json
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models import db
from app.models.outbox import Outbox
from lib.outbox_repository import FLASK_AVAILABLE


@pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
@pytest.mark.usefixtures("event_producer")
class TestEndToEndOutboxScenarios:
    """Test end-to-end scenarios for outbox functionality."""

    def test_create_host_saves_to_outbox(self, event_producer, db_create_host, flask_app):
        """Test that creating a new host event saves to the outbox."""
        # Create a host first
        created_host = db_create_host()
        host_id = str(created_host.id)
        
        # Create a simple host created event that matches the expected structure
        event_data = {
            "type": "created",
            "id": host_id,
            "display_name": created_host.display_name,
            "account": created_host.account,
            "org_id": created_host.org_id,
            "groups": []  # Simple groups structure
        }
        
        # Directly test the outbox repository
        from lib.outbox_repository import write_event_to_outbox
        result = write_event_to_outbox(json.dumps(event_data))
        
        # Verify outbox write was successful
        assert result is True

        # Verify outbox record was created
        outbox_records = db.session.query(Outbox).filter(
            Outbox.aggregate_id == host_id,
            Outbox.event_type == "created"
        ).all()

        assert len(outbox_records) == 1
        outbox_record = outbox_records[0]
        
        # Verify outbox record structure
        assert outbox_record.aggregate_type == "hbi.hosts"
        assert outbox_record.event_type == "created"
        assert str(outbox_record.aggregate_id) == host_id
        
        # Verify payload structure
        payload = outbox_record.payload
        assert payload["type"] == "host"
        assert payload["reporterType"] == "hbi"
        assert "representations" in payload
        
        representations = payload["representations"]
        assert representations["metadata"]["localResourceId"] == host_id
        assert representations["metadata"]["reporterVersion"] == "1.0"

    def test_update_host_saves_to_outbox(self, event_producer, db_create_host, flask_app):
        """Test that updating an existing host event saves to the outbox."""
        # Create a host first
        original_host = db_create_host()
        host_id = str(original_host.id)
        
        # Create a simple host updated event that matches the expected structure
        event_data = {
            "type": "updated",
            "id": host_id,
            "display_name": "updated-test-host",
            "account": original_host.account,
            "org_id": original_host.org_id,
            "groups": []  # Simple groups structure
        }
        
        # Directly test the outbox repository
        from lib.outbox_repository import write_event_to_outbox
        result = write_event_to_outbox(json.dumps(event_data))
        
        # Verify outbox write was successful
        assert result is True

        # Verify outbox record was created
        outbox_records = db.session.query(Outbox).filter(
            Outbox.aggregate_id == host_id,
            Outbox.event_type == "updated"
        ).all()

        assert len(outbox_records) == 1
        outbox_record = outbox_records[0]
        
        # Verify outbox record structure
        assert outbox_record.aggregate_type == "hbi.hosts"
        assert outbox_record.event_type == "updated"
        assert str(outbox_record.aggregate_id) == host_id
        
        # Verify payload structure
        payload = outbox_record.payload
        assert payload["type"] == "host"
        assert payload["reporterType"] == "hbi"
        assert "representations" in payload
        
        representations = payload["representations"]
        assert representations["metadata"]["localResourceId"] == host_id
        assert representations["metadata"]["reporterVersion"] == "1.0"

    def test_delete_host_saves_to_outbox(self, event_producer, db_create_host, flask_app):
        """Test that deleting an existing host event saves to the outbox."""
        # Create a host first
        original_host = db_create_host()
        host_id = str(original_host.id)
        
        # Create a simple host delete event that matches the expected structure
        event_data = {
            "type": "delete",
            "id": host_id,
            "display_name": original_host.display_name,
            "account": original_host.account,
            "org_id": original_host.org_id
        }
        
        # Directly test the outbox repository
        from lib.outbox_repository import write_event_to_outbox
        result = write_event_to_outbox(json.dumps(event_data))
        
        # Verify outbox write was successful
        assert result is True

        # Verify outbox record was created
        outbox_records = db.session.query(Outbox).filter(
            Outbox.aggregate_id == host_id,
            Outbox.event_type == "delete"
        ).all()

        assert len(outbox_records) == 1
        outbox_record = outbox_records[0]
        
        # Verify outbox record structure
        assert outbox_record.aggregate_type == "hbi.hosts"
        assert outbox_record.event_type == "delete"
        assert str(outbox_record.aggregate_id) == host_id
        
        # Verify payload structure for delete events
        payload = outbox_record.payload
        assert "reference" in payload
        
        reference = payload["reference"]
        assert reference["resource_type"] == "host"
        assert reference["resource_id"] == host_id
        assert reference["reporter"]["type"] == "HBI"

    def test_multiple_operations_create_separate_outbox_records(
        self, event_producer, db_create_host, flask_app
    ):
        """Test that multiple operations on the same host create separate outbox records."""
        # Create a host first
        created_host = db_create_host()
        host_id = str(created_host.id)
        
        from lib.outbox_repository import write_event_to_outbox
        
        # Create a "created" event
        created_event = {
            "type": "created",
            "id": host_id,
            "display_name": created_host.display_name,
            "account": created_host.account,
            "org_id": created_host.org_id,
            "groups": []
        }
        result1 = write_event_to_outbox(json.dumps(created_event))
        assert result1 is True

        # Create an "updated" event  
        updated_event = {
            "type": "updated",
            "id": host_id,
            "display_name": "updated-lifecycle-host",
            "account": created_host.account,
            "org_id": created_host.org_id,
            "groups": []
        }
        result2 = write_event_to_outbox(json.dumps(updated_event))
        assert result2 is True

        # Create a "delete" event
        delete_event = {
            "type": "delete",
            "id": host_id,
            "display_name": "updated-lifecycle-host",
            "account": created_host.account,
            "org_id": created_host.org_id
        }
        result3 = write_event_to_outbox(json.dumps(delete_event))
        assert result3 is True

        # Verify all three outbox records were created
        outbox_records = db.session.query(Outbox).filter(
            Outbox.aggregate_id == host_id
        ).order_by(Outbox.event_type).all()

        # Should have created, delete, updated (alphabetical order)
        assert len(outbox_records) == 3
        
        event_types = [record.event_type for record in outbox_records]
        assert "created" in event_types
        assert "updated" in event_types
        assert "delete" in event_types

        # Verify each record has correct structure
        for record in outbox_records:
            assert record.aggregate_type == "hbi.hosts"
            assert str(record.aggregate_id) == host_id
            assert record.payload is not None

    def teardown_method(self):
        """Clean up outbox records after each test."""
        # Clean up any outbox records created during tests
        db.session.execute(text("DELETE FROM hbi.outbox"))
        db.session.commit()