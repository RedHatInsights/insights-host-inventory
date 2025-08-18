"""
End-to-end tests for outbox functionality.

These tests cover the complete outbox workflow including:
- Event creation and validation
- Database persistence
- Error handling and rollback scenarios
- Metrics tracking
- Schema validation
"""

import json
import uuid
from unittest.mock import Mock, patch

import pytest
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import OutboxSaveException
from app.models.database import db
from app.models.host import Host
from app.models.outbox import Outbox
from app.models.schemas import OutboxSchema
from lib.outbox_repository import write_event_to_outbox
from tests.helpers.test_utils import SYSTEM_IDENTITY, generate_uuid


class TestOutboxE2ECases:
    """End-to-end test cases for outbox functionality."""

    def test_successful_created_event_e2e(self, db_create_host, db_get_host):
        """Test complete flow for a successful 'created' event."""
        # Create a host with all required fields
        host_data = {
            "canonical_facts": {
                "insights_id": generate_uuid(),
                "subscription_manager_id": generate_uuid(),
                "fqdn": "test-host.example.com",
            },
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        }
        
        created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
        host_id = str(created_host.id)
        
        # Retrieve the host to ensure it has groups
        host = db_get_host(created_host.id)
        
        # Write created event to outbox
        result = write_event_to_outbox("created", host_id, host)
        
        # Verify the operation succeeded
        assert result is True
        
        # Verify outbox entry was created in database
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1
        
        outbox_entry = outbox_entries[0]
        assert outbox_entry.aggregatetype == "hbi.hosts"
        assert str(outbox_entry.aggregateid) == host_id
        assert outbox_entry.operation == "ReportResource"
        assert outbox_entry.version == "v1beta2"
        
        # Verify payload structure
        payload = outbox_entry.payload
        assert payload["type"] == "host"
        assert payload["reporterType"] == "hbi"
        assert payload["reporterInstanceId"] == "redhat.com"
        
        # Verify representations
        representations = payload["representations"]
        assert "metadata" in representations
        assert "common" in representations
        assert "reporter" in representations
        
        # Verify metadata
        metadata = representations["metadata"]
        assert metadata["localResourceId"] == host_id
        assert metadata["apiHref"] == "https://apiHref.com/"
        assert metadata["consoleHref"] == "https://www.console.com/"
        assert metadata["reporterVersion"] == "1.0"
        
        # Verify reporter data
        reporter = representations["reporter"]
        assert reporter["insights_id"] == str(host.insights_id) if host.insights_id else None
        assert reporter["subscription_manager_id"] == host.subscription_manager_id
        assert reporter["satellite_id"] == host.satellite_id
        assert reporter["ansible_host"] == host.ansible_host

    def test_successful_updated_event_e2e(self, db_create_host, db_get_host):
        """Test complete flow for a successful 'updated' event."""
        # Create a host
        host_data = {
            "canonical_facts": {
                "insights_id": generate_uuid(),
                "subscription_manager_id": generate_uuid(),
            },
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        }
        
        created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        # Write updated event to outbox
        result = write_event_to_outbox("updated", host_id, host)
        
        # Verify the operation succeeded
        assert result is True
        
        # Verify outbox entry was created
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1
        
        outbox_entry = outbox_entries[0]
        assert outbox_entry.operation == "ReportResource"
        assert outbox_entry.payload["type"] == "host"

    def test_successful_delete_event_e2e(self, db_create_host):
        """Test complete flow for a successful 'delete' event."""
        # Create a host first
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        
        # Write delete event to outbox (no host object needed for delete)
        result = write_event_to_outbox("delete", host_id)
        
        # Verify the operation succeeded
        assert result is True
        
        # Verify outbox entry was created
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1
        
        outbox_entry = outbox_entries[0]
        assert outbox_entry.operation == "DeleteResource"
        assert outbox_entry.version == "v1beta2"
        
        # Verify delete payload structure
        payload = outbox_entry.payload
        assert "reference" in payload
        
        reference = payload["reference"]
        assert reference["resource_type"] == "host"
        assert reference["resource_id"] == host_id
        assert reference["reporter"]["type"] == "HBI"

    def test_multiple_events_same_host_e2e(self, db_create_host, db_get_host):
        """Test multiple events for the same host create separate outbox entries."""
        # Create a host
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        # Write multiple events
        write_event_to_outbox("created", host_id, host)
        write_event_to_outbox("updated", host_id, host)
        write_event_to_outbox("delete", host_id)
        
        # Verify all entries were created
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 3
        
        operations = [entry.operation for entry in outbox_entries]
        assert "ReportResource" in operations  # created/updated use this
        assert "DeleteResource" in operations
        assert operations.count("ReportResource") == 2  # created and updated

    def test_invalid_event_type_error(self, db_create_host):
        """Test error handling for invalid event types."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("invalid_event", host_id)
        
        assert "Invalid event type" in str(exc_info.value)
        
        # Verify no outbox entry was created
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 0

    def test_missing_event_parameter_error(self, db_create_host):
        """Test error handling for missing event parameter."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("", host_id)
        
        assert "Missing required field 'event'" in str(exc_info.value)

    def test_missing_host_id_parameter_error(self):
        """Test error handling for missing host_id parameter."""
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("created", "")
        
        assert "Missing required field 'host_id'" in str(exc_info.value)

    def test_missing_host_for_created_event_error(self, db_create_host):
        """Test error handling when host object is missing for created event."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("created", host_id, None)
        
        # The error message is wrapped in an "Unexpected error" message
        assert "Missing required 'host data'" in str(exc_info.value) or "Missing required 'host data'" in exc_info.value.detail

    def test_missing_host_for_updated_event_error(self, db_create_host):
        """Test error handling when host object is missing for updated event."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("updated", host_id, None)
        
        # The error message is wrapped in an "Unexpected error" message
        assert "Missing required 'host data'" in str(exc_info.value) or "Missing required 'host data'" in exc_info.value.detail

    def test_host_without_id_error(self, db_create_host):
        """Test error handling when host object has no ID."""
        # Create a host object without setting the ID
        host_data = {
            "canonical_facts": {
                "insights_id": generate_uuid(),
                "subscription_manager_id": generate_uuid(),
            }
        }
        host_without_id = Host(
            canonical_facts=host_data["canonical_facts"],
            reporter="test-reporter"
        )
        host_without_id.id = None  # Explicitly set to None
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("created", "some-id", host_without_id)
        
        # The error message is wrapped in an "Unexpected error" message
        assert "Missing required field 'id' in host data" in str(exc_info.value) or "Missing required field 'id' in host data" in exc_info.value.detail

    def test_invalid_host_id_format_error(self):
        """Test error handling for invalid host_id format."""
        host_data = {
            "canonical_facts": {
                "insights_id": generate_uuid(),
                "subscription_manager_id": generate_uuid(),
            }
        }
        host = Host(
            canonical_facts=host_data["canonical_facts"],
            reporter="test-reporter"
        )
        host.id = uuid.uuid4()
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("delete", "invalid-uuid-format")
        
        # The error should be caught during schema validation
        assert "OutboxSaveException" in str(type(exc_info.value))

    @patch('lib.outbox_repository.OutboxSchema')
    def test_schema_validation_error(self, mock_schema, db_create_host, db_get_host):
        """Test error handling for schema validation failures."""
        # Mock schema to raise validation error
        mock_schema_instance = Mock()
        mock_schema_instance.load.side_effect = MarshmallowValidationError("Invalid data")
        mock_schema.return_value = mock_schema_instance
        
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox("created", host_id, host)
        
        assert "Invalid host or event was provided" in str(exc_info.value)

    def test_database_error_handling(self, db_create_host, db_get_host):
        """Test error handling for database errors."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        # Mock database error only for the outbox add operation
        with patch('lib.outbox_repository.db.session.add') as mock_add:
            mock_add.side_effect = SQLAlchemyError("Database connection failed")
            
            with pytest.raises(OutboxSaveException) as exc_info:
                write_event_to_outbox("created", host_id, host)
            
            assert "Failed to save event to outbox" in str(exc_info.value)

    def test_table_not_exists_error_handling(self, db_create_host, db_get_host):
        """Test specific error handling for missing outbox table."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        # Mock table doesn't exist error only for the outbox add operation
        with patch('lib.outbox_repository.db.session.add') as mock_add:
            mock_add.side_effect = SQLAlchemyError("table 'outbox' does not exist")
            
            with pytest.raises(OutboxSaveException) as exc_info:
                write_event_to_outbox("created", host_id, host)
            
            assert "Failed to save event to outbox" in str(exc_info.value)

    @patch('lib.outbox_repository.outbox_save_success')
    def test_success_metrics_tracking(self, mock_success_metric, db_create_host, db_get_host):
        """Test that success metrics are properly tracked."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        result = write_event_to_outbox("created", host_id, host)
        
        assert result is True
        mock_success_metric.inc.assert_called_once()

    @patch('lib.outbox_repository.outbox_save_failure')
    def test_failure_metrics_tracking(self, mock_failure_metric):
        """Test that failure metrics are properly tracked."""
        with pytest.raises(OutboxSaveException):
            write_event_to_outbox("invalid_event", "some-host-id")
        
        mock_failure_metric.inc.assert_called()

    def test_outbox_schema_validation_success(self):
        """Test that valid outbox entries pass schema validation."""
        # Test created/updated payload
        created_payload = {
            "aggregatetype": "hbi.hosts",
            "aggregateid": str(uuid.uuid4()),
            "operation": "ReportResource",
            "version": "v1beta2",
            "payload": {
                "type": "host",
                "reporterType": "hbi",
                "reporterInstanceId": "redhat.com",
                "representations": {
                    "metadata": {
                        "localResourceId": str(uuid.uuid4()),
                        "apiHref": "https://apiHref.com/",
                        "consoleHref": "https://www.console.com/",
                        "reporterVersion": "1.0"
                    },
                    "common": {},
                    "reporter": {
                        "satellite_id": None,
                        "subscription_manager_id": str(uuid.uuid4()),
                        "insights_id": str(uuid.uuid4()),
                        "ansible_host": None
                    }
                }
            }
        }
        
        schema = OutboxSchema()
        validated_data = schema.load(created_payload)
        assert validated_data is not None
        
        # Test delete payload
        delete_payload = {
            "aggregatetype": "hbi.hosts",
            "aggregateid": str(uuid.uuid4()),
            "operation": "DeleteResource",
            "version": "v1beta2",
            "payload": {
                "reference": {
                    "resource_type": "host",
                    "resource_id": str(uuid.uuid4()),
                    "reporter": {
                        "type": "HBI"
                    }
                }
            }
        }
        
        validated_delete_data = schema.load(delete_payload)
        assert validated_delete_data is not None

    def test_outbox_entry_with_groups(self, db_create_host, db_create_group, db_get_host, db_create_host_group_assoc):
        """Test outbox entry creation when host has groups."""
        # Create a group first
        group = db_create_group("test-group", SYSTEM_IDENTITY)
        
        # Create a host
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        
        # Associate host with group
        db_create_host_group_assoc(host_id, group.id)
        
        # Get the host with groups
        host = db_get_host(created_host.id)
        
        # Write created event to outbox
        result = write_event_to_outbox("created", host_id, host)
        
        assert result is True
        
        # Verify outbox entry contains group information
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1
        
        payload = outbox_entries[0].payload
        common = payload["representations"]["common"]
        
        # Should contain workspace_id from the first group
        assert "workspace_id" in common
        assert common["workspace_id"] == host.groups[0]["id"]

    def test_transaction_rollback_behavior(self, db_create_host, db_get_host):
        """Test that outbox entries are part of the same transaction."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        # Use nested transaction to test rollback
        try:
            with db.session.begin_nested():
                # Write to outbox (should be part of this transaction)
                result = write_event_to_outbox("created", host_id, host)
                assert result is True
                
                # Verify entry exists in current transaction
                outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
                assert len(outbox_entries) == 1
                
                # Force rollback
                raise Exception("Force rollback")
                
        except Exception:
            # Expected exception to trigger rollback
            pass
        
        # Verify entry was rolled back
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 0

    def test_concurrent_outbox_writes(self, db_create_host, db_get_host):
        """Test that multiple outbox writes for different hosts work correctly."""
        # Create multiple hosts
        host1 = db_create_host(SYSTEM_IDENTITY)
        host2 = db_create_host(SYSTEM_IDENTITY)
        host3 = db_create_host(SYSTEM_IDENTITY)
        
        host1_obj = db_get_host(host1.id)
        host2_obj = db_get_host(host2.id)
        host3_obj = db_get_host(host3.id)
        
        # Write events for all hosts
        write_event_to_outbox("created", str(host1.id), host1_obj)
        write_event_to_outbox("updated", str(host2.id), host2_obj)
        write_event_to_outbox("delete", str(host3.id))
        
        # Flush the session to make entries visible
        db.session.flush()
        
        # Verify all entries were created
        all_entries = db.session.query(Outbox).all()
        host_ids = [str(entry.aggregateid) for entry in all_entries]
        
        assert str(host1.id) in host_ids
        assert str(host2.id) in host_ids
        assert str(host3.id) in host_ids
        
        # Verify operations are correct
        operations_by_host = {
            str(entry.aggregateid): entry.operation for entry in all_entries
        }
        
        assert operations_by_host[str(host1.id)] == "ReportResource"
        assert operations_by_host[str(host2.id)] == "ReportResource"
        assert operations_by_host[str(host3.id)] == "DeleteResource"

    def test_payload_json_serialization(self, db_create_host, db_get_host):
        """Test that outbox payloads are properly JSON serializable."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        write_event_to_outbox("created", host_id, host)
        
        # Flush to make entry visible
        db.session.flush()
        
        outbox_entry = db.session.query(Outbox).filter_by(aggregateid=host_id).first()
        
        # Verify payload can be serialized to JSON
        payload_json = json.dumps(outbox_entry.payload)
        assert payload_json is not None
        
        # Verify it can be deserialized back
        deserialized_payload = json.loads(payload_json)
        assert deserialized_payload == outbox_entry.payload

    def test_outbox_entry_uuid_generation(self, db_create_host, db_get_host):
        """Test that outbox entries get proper UUID generation."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)
        
        write_event_to_outbox("created", host_id, host)
        
        # Flush to make entry visible
        db.session.flush()
        
        outbox_entry = db.session.query(Outbox).filter_by(aggregateid=host_id).first()
        
        # Verify outbox entry has a valid UUID
        assert outbox_entry.id is not None
        assert isinstance(outbox_entry.id, uuid.UUID)
        
        # Verify aggregateid is also a valid UUID
        assert isinstance(outbox_entry.aggregateid, uuid.UUID)
        assert str(outbox_entry.aggregateid) == host_id
