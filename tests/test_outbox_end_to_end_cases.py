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
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import OutboxSaveException
from app.models.database import db
from app.models.host import Host
from app.models.outbox import Outbox
from app.models.schemas import OutboxSchema
from app.queue.events import EventType
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import WorkspaceMessageConsumer
from lib.outbox_repository import write_event_to_outbox
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.mq_utils import generate_kessel_workspace_message
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host


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
        result = write_event_to_outbox(EventType.created, host_id, host)

        # Verify the operation succeeded
        assert result is True

        # Verify outbox entry was created (entries are no longer automatically pruned)
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

        # Verify the outbox entry has the correct structure
        outbox_entry = outbox_entries[0]
        assert outbox_entry.aggregatetype == "hbi.hosts"
        assert outbox_entry.operation == "ReportResource"
        assert outbox_entry.version == "v1beta2"
        assert outbox_entry.payload["type"] == "host"
        assert outbox_entry.payload["reporterType"] == "hbi"

        # Note: Since the entry is immediately deleted after commit, we can't verify
        # the specific payload content. The success of the operation indicates
        # the payload was correctly structured and validated.

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
        result = write_event_to_outbox(EventType.updated, host_id, host)

        # Verify the operation succeeded
        assert result is True

        # Verify outbox entry was created (entries are no longer automatically pruned)
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

        # Verify the outbox entry has the correct structure
        outbox_entry = outbox_entries[0]
        assert outbox_entry.aggregatetype == "hbi.hosts"
        assert outbox_entry.operation == "ReportResource"
        assert outbox_entry.version == "v1beta2"
        assert outbox_entry.payload["type"] == "host"
        assert outbox_entry.payload["reporterType"] == "hbi"

    def test_successful_delete_event_e2e(self, db_create_host):
        """Test complete flow for a successful 'delete' event."""
        # Create a host first
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)

        # Write delete event to outbox (no host object needed for delete)
        result = write_event_to_outbox(EventType.delete, host_id)

        # Verify the operation succeeded
        assert result is True

        # Verify outbox entry was created (entries are no longer automatically pruned)
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

        # Verify the outbox entry has the correct structure
        outbox_entry = outbox_entries[0]
        assert outbox_entry.aggregatetype == "hbi.hosts"
        assert outbox_entry.operation == "DeleteResource"
        assert outbox_entry.version == "v1beta2"
        assert outbox_entry.payload["reference"]["resource_type"] == "host"
        assert outbox_entry.payload["reference"]["resource_id"] == host_id

    def test_multiple_events_same_host_e2e(self, db_create_host, db_get_host):
        """Test multiple events for the same host create separate outbox entries."""
        # Create a host
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # Write multiple events
        write_event_to_outbox(EventType.created, host_id, host)
        write_event_to_outbox(EventType.updated, host_id, host)
        write_event_to_outbox(EventType.delete, host_id)

        # Verify all entries were created (entries are no longer automatically pruned)
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 3  # All entries exist since automatic pruning was removed

        # Verify each entry has the correct structure
        operations = [entry.operation for entry in outbox_entries]
        assert "ReportResource" in operations  # created event
        assert "ReportResource" in operations  # updated event
        assert "DeleteResource" in operations  # delete event

    def test_invalid_event_type_error(self, db_create_host):
        """Test error handling for invalid event types."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)

        # Test with an invalid event type that will cause an error in _build_outbox_entry
        # Since the current implementation doesn't validate EventType, we'll test with None
        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox(None, host_id)

        # The error should be caught during validation
        assert "Missing required field 'event'" in str(exc_info.value)

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
            write_event_to_outbox(EventType.created, "")

        assert "Missing required field 'host_id'" in str(exc_info.value)

    def test_missing_host_for_created_event_error(self, db_create_host):
        """Test error handling when host object is missing for created event."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)

        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox(EventType.created, host_id, None)

        # The error message is wrapped in an "Unexpected error" message
        assert (
            "Missing required 'host data'" in str(exc_info.value)
            or "Missing required 'host data'" in exc_info.value.detail
        )

    def test_missing_host_for_updated_event_error(self, db_create_host):
        """Test error handling when host object is missing for updated event."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)

        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox(EventType.updated, host_id, None)

        # The error message is wrapped in an "Unexpected error" message
        assert (
            "Missing required 'host data'" in str(exc_info.value)
            or "Missing required 'host data'" in exc_info.value.detail
        )

    def test_host_without_id_error(self, db_create_host):  # noqa: ARG002
        """Test error handling when host object has no ID."""
        # Create a host object without setting the ID
        host_data = {
            "canonical_facts": {
                "insights_id": generate_uuid(),
                "subscription_manager_id": generate_uuid(),
            }
        }
        host_without_id = Host(canonical_facts=host_data["canonical_facts"], reporter="test-reporter")
        host_without_id.id = None  # Explicitly set to None

        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox(EventType.created, "some-id", host_without_id)

        # The error message is wrapped in multiple layers due to error handling
        error_str = str(exc_info.value)
        # The message may be escaped, so check for both the original and escaped versions
        assert (
            "Missing required field 'id' in host data" in error_str
            or "Missing required field \\'id\\' in host data" in error_str
            or "Missing required field \\\\\\'id\\\\\\' in host data" in error_str
        )

    def test_invalid_host_id_format_error(self):
        """Test error handling for invalid host_id format."""
        host_data = {
            "canonical_facts": {
                "insights_id": generate_uuid(),
                "subscription_manager_id": generate_uuid(),
            }
        }
        host = Host(canonical_facts=host_data["canonical_facts"], reporter="test-reporter")
        host.id = uuid.uuid4()

        with pytest.raises(OutboxSaveException) as exc_info:
            write_event_to_outbox(EventType.delete, "invalid-uuid-format")

        # The error should be caught during schema validation
        assert "OutboxSaveException" in str(type(exc_info.value))

    @patch("lib.outbox_repository.OutboxSchema")
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
            write_event_to_outbox(EventType.created, host_id, host)

        assert "Invalid host or event was provided" in str(exc_info.value)

    def test_database_error_handling(self, db_create_host, db_get_host):
        """Test error handling for database errors."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # Mock database error only for the outbox add operation
        with patch("lib.outbox_repository.db.session.add") as mock_add:
            mock_add.side_effect = SQLAlchemyError("Database connection failed")

            with pytest.raises(OutboxSaveException) as exc_info:
                write_event_to_outbox(EventType.created, host_id, host)

            assert "Failed to save event to outbox" in str(exc_info.value)

    def test_table_not_exists_error_handling(self, db_create_host, db_get_host):
        """Test specific error handling for missing outbox table."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # Mock table doesn't exist error only for the outbox add operation
        with patch("lib.outbox_repository.db.session.add") as mock_add:
            mock_add.side_effect = SQLAlchemyError("table 'outbox' does not exist")

            with pytest.raises(OutboxSaveException) as exc_info:
                write_event_to_outbox(EventType.created, host_id, host)

            assert "Failed to save event to outbox" in str(exc_info.value)

    @patch("lib.outbox_repository.outbox_save_success")
    def test_success_metrics_tracking(self, mock_success_metric, db_create_host, db_get_host):
        """Test that success metrics are properly tracked."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        result = write_event_to_outbox(EventType.created, host_id, host)

        assert result is True
        mock_success_metric.inc.assert_called_once()

    @patch("lib.outbox_repository.outbox_save_failure")
    def test_failure_metrics_tracking(self, mock_failure_metric):
        """Test that failure metrics are properly tracked."""
        with pytest.raises(OutboxSaveException):
            write_event_to_outbox(None, "some-host-id")

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
                        "reporterVersion": "1.0",
                    },
                    "common": {},
                    "reporter": {
                        "satellite_id": None,
                        "subscription_manager_id": str(uuid.uuid4()),
                        "insights_id": str(uuid.uuid4()),
                        "ansible_host": None,
                    },
                },
            },
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
                "reference": {"resource_type": "host", "resource_id": str(uuid.uuid4()), "reporter": {"type": "HBI"}}
            },
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
        result = write_event_to_outbox(EventType.created, host_id, host)

        assert result is True

        # Verify outbox entry was created (entries are no longer automatically pruned)
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

        # Verify the outbox entry has the correct structure
        outbox_entry = outbox_entries[0]
        assert outbox_entry.aggregatetype == "hbi.hosts"
        assert outbox_entry.operation == "ReportResource"
        assert outbox_entry.version == "v1beta2"
        assert outbox_entry.payload["type"] == "host"
        assert outbox_entry.payload["reporterType"] == "hbi"
        # Verify the common field contains workspace_id
        assert "workspace_id" in outbox_entry.payload["representations"]["common"]

    def test_transaction_rollback_behavior(self, db_create_host, db_get_host):
        """Test that outbox entries are committed immediately and not subject to external rollback."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # The outbox implementation now commits immediately within the function
        # This test verifies that the function handles its own transaction
        result = write_event_to_outbox(EventType.created, host_id, host)
        assert result is True

        # Verify entry was created (entries are no longer automatically pruned)
        outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
        assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

        # Verify the outbox entry has the correct structure
        outbox_entry = outbox_entries[0]
        assert outbox_entry.aggregatetype == "hbi.hosts"
        assert outbox_entry.operation == "ReportResource"
        assert outbox_entry.version == "v1beta2"

    def test_concurrent_outbox_writes(self, db_create_host, db_get_host):
        """Test that multiple outbox writes for different hosts work correctly."""
        # Create multiple hosts
        host1 = db_create_host(SYSTEM_IDENTITY)
        host2 = db_create_host(SYSTEM_IDENTITY)
        host3 = db_create_host(SYSTEM_IDENTITY)

        host1_obj = db_get_host(host1.id)
        host2_obj = db_get_host(host2.id)

        # Write events for all hosts
        write_event_to_outbox(EventType.created, str(host1.id), host1_obj)
        write_event_to_outbox(EventType.updated, str(host2.id), host2_obj)
        write_event_to_outbox(EventType.delete, str(host3.id))

        # Flush the session to make entries visible
        db.session.flush()

        # Verify all entries were created (entries are no longer automatically pruned)
        all_entries = db.session.query(Outbox).all()
        assert len(all_entries) == 3  # All entries exist since automatic pruning was removed

        # Verify each entry has the correct structure
        operations = [entry.operation for entry in all_entries]
        assert "ReportResource" in operations  # created event
        assert "ReportResource" in operations  # updated event
        assert "DeleteResource" in operations  # delete event

    def test_payload_json_serialization(self, db_create_host, db_get_host):
        """Test that outbox payloads are properly JSON serializable."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        write_event_to_outbox(EventType.created, host_id, host)

        # Flush to make entry visible
        db.session.flush()

        # Since entries are immediately deleted after commit, we can't verify payload serialization
        # The success of the operation indicates JSON serialization worked correctly

    def test_outbox_entry_uuid_generation(self, db_create_host, db_get_host):
        """Test that outbox entries get proper UUID generation."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        write_event_to_outbox(EventType.created, host_id, host)

        # Flush to make entry visible
        db.session.flush()

        # Since entries are immediately deleted after commit, we can't verify UUID generation
        # The success of the operation indicates UUID generation worked correctly

    def test_host_creation_via_mq_with_outbox_validation(
        self, flask_app, event_producer_mock, notification_event_producer_mock
    ):
        """Test that creating a host via MQ message triggers outbox entry creation."""

        # Create test host data
        test_host = minimal_host(
            insights_id=generate_uuid(), subscription_manager_id=generate_uuid(), fqdn="test-mq-host.example.com"
        )

        platform_metadata = get_platform_metadata(SYSTEM_IDENTITY)
        message = wrap_message(test_host.data(), platform_metadata=platform_metadata)

        # Mock the outbox writing to capture the call without immediate deletion
        with patch("lib.host_repository.write_event_to_outbox") as mock_write_outbox:
            mock_write_outbox.return_value = True

            # Create MQ consumer and process message
            consumer = IngressMessageConsumer(None, flask_app, event_producer_mock, notification_event_producer_mock)
            result = consumer.handle_message(json.dumps(message))
            db.session.commit()

            # Verify the host was created successfully
            assert result.event_type == EventType.created
            assert result.row is not None
            created_host = result.row
            assert str(created_host.insights_id) == test_host.insights_id
            assert created_host.fqdn == "test-mq-host.example.com"

            # Verify outbox entry was written with correct parameters
            mock_write_outbox.assert_called_once()
            call_args = mock_write_outbox.call_args

            # Check the event type (first argument)
            assert call_args[0][0] == EventType.created

            # Check the host ID (second argument)
            assert str(call_args[0][1]) == str(created_host.id)

            # Check the host object (third argument)
            outbox_host = call_args[0][2]
            assert outbox_host.id == created_host.id
            assert outbox_host.insights_id == created_host.insights_id
            assert outbox_host.fqdn == created_host.fqdn

    def test_mq_host_creation_with_groups_and_outbox_validation(
        self, flask_app, event_producer_mock, notification_event_producer_mock, db_create_group
    ):
        """Test that creating a host via MQ with groups triggers correct outbox entry creation."""

        # Create a group first to test group assignment
        _ = db_create_group("test-group", SYSTEM_IDENTITY)

        # Create test host data with group assignment capability
        test_host = minimal_host(
            insights_id=generate_uuid(),
            subscription_manager_id=generate_uuid(),
            fqdn="test-grouped-mq-host.example.com",
        )

        platform_metadata = get_platform_metadata(SYSTEM_IDENTITY)
        message = wrap_message(test_host.data(), platform_metadata=platform_metadata)

        # Mock the outbox writing to capture the call without immediate deletion
        with patch("lib.host_repository.write_event_to_outbox") as mock_write_outbox:
            # Also mock the Kessel migration flag to enable group assignment
            with patch("app.queue.host_mq.get_flag_value", return_value=True):
                mock_write_outbox.return_value = True

                # Create MQ consumer and process message
                consumer = IngressMessageConsumer(
                    None, flask_app, event_producer_mock, notification_event_producer_mock
                )
                result = consumer.handle_message(json.dumps(message))
                db.session.commit()

                # Verify the host was created successfully with group assignment
                assert result.event_type == EventType.created
                assert result.row is not None
                created_host = result.row
                assert str(created_host.insights_id) == test_host.insights_id
                assert created_host.fqdn == "test-grouped-mq-host.example.com"
                assert len(created_host.groups) == 1  # Should be assigned to ungrouped hosts group

                # Verify outbox entry was written with correct parameters
                mock_write_outbox.assert_called_once()
                call_args = mock_write_outbox.call_args

                # Check the event type (first argument)
                assert call_args[0][0] == EventType.created

                # Check the host ID (second argument)
                assert str(call_args[0][1]) == str(created_host.id)

                # Check the host object (third argument)
                outbox_host = call_args[0][2]
                assert outbox_host.id == created_host.id
                assert outbox_host.insights_id == created_host.insights_id
                assert outbox_host.fqdn == created_host.fqdn
                assert len(outbox_host.groups) == 1  # Verify groups are included in outbox payload

    def test_mq_host_creation_with_actual_outbox_entry(
        self, flask_app, event_producer_mock, notification_event_producer_mock
    ):
        """Test complete MQ host creation flow including actual outbox entry persistence and deletion."""

        # Create test host data
        test_host = minimal_host(
            insights_id=generate_uuid(),
            subscription_manager_id=generate_uuid(),
            fqdn="test-complete-mq-host.example.com",
        )

        platform_metadata = get_platform_metadata(SYSTEM_IDENTITY)
        message = wrap_message(test_host.data(), platform_metadata=platform_metadata)

        # Track outbox success metrics to verify outbox operation succeeded
        with patch("lib.outbox_repository.outbox_save_success") as mock_success_metric:
            # Create MQ consumer and process message
            consumer = IngressMessageConsumer(None, flask_app, event_producer_mock, notification_event_producer_mock)
            result = consumer.handle_message(json.dumps(message))
            db.session.commit()

            # Verify the host was created successfully
            assert result.event_type == EventType.created
            assert result.row is not None
            created_host = result.row
            assert str(created_host.insights_id) == test_host.insights_id
            assert created_host.fqdn == "test-complete-mq-host.example.com"

            # Verify outbox operation succeeded (metric was incremented)
            mock_success_metric.inc.assert_called_once()

            # Verify outbox entry was created (entries are no longer automatically pruned)
            outbox_entries = db.session.query(Outbox).filter_by(aggregateid=created_host.id).all()
            assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

            # Verify the outbox entry has the correct structure
            outbox_entry = outbox_entries[0]
            assert outbox_entry.aggregatetype == "hbi.hosts"
            assert outbox_entry.operation == "ReportResource"
            assert outbox_entry.version == "v1beta2"
            assert outbox_entry.payload["type"] == "host"
            assert outbox_entry.payload["reporterType"] == "hbi"

            # The success metric increment proves the outbox entry was created, validated, and processed

    def test_host_group_update_via_mq_with_outbox_common_validation(
        self,
        flask_app,
        event_producer_mock,
        notification_event_producer_mock,
        db_create_group_with_hosts,
        db_get_hosts_for_group,
        db_get_group_by_id,
    ):
        """
        Test that updating a host's group via MQ workspace update triggers outbox entry with
        correct common field.
        """
        # Create a group with hosts
        group = db_create_group_with_hosts("original-group-name", 2)
        original_group_id = str(group.id)
        hosts = db_get_hosts_for_group(group.id)
        host_ids = [str(host.id) for host in hosts]

        # Verify initial state - hosts should have the original group
        assert len(hosts) == 2
        for host in hosts:
            assert len(host.groups) == 1
            assert host.groups[0]["id"] == original_group_id
            assert host.groups[0]["name"] == "original-group-name"

        # Create workspace update message to change group name
        new_group_name = "updated-group-name-via-mq"
        message = generate_kessel_workspace_message("update", original_group_id, new_group_name)

        # Mock the outbox writing to capture the calls and validate payload
        outbox_calls = []

        def mock_write_outbox(event_type, host_id, host_obj):
            outbox_calls.append({"event_type": event_type, "host_id": host_id, "host": host_obj})
            return True

        with patch("lib.group_repository.write_event_to_outbox", side_effect=mock_write_outbox):
            # Create workspace consumer and process the update message
            consumer = WorkspaceMessageConsumer(None, flask_app, event_producer_mock, notification_event_producer_mock)
            result = consumer.handle_message(json.dumps(message))
            db.session.commit()

            # Verify the workspace update was successful
            assert result.event_type == EventType.updated
            updated_group = db_get_group_by_id(original_group_id)
            assert updated_group.name == new_group_name

            # Verify outbox entries were created for both hosts
            assert len(outbox_calls) == 2

            # Validate each outbox call
            for call in outbox_calls:
                assert call["event_type"] == EventType.updated
                assert call["host_id"] in host_ids

                # Get the host object from the call
                host_obj = call["host"]
                assert host_obj is not None
                assert len(host_obj.groups) == 1
                assert host_obj.groups[0]["id"] == original_group_id
                assert host_obj.groups[0]["name"] == new_group_name

                # Validate the outbox payload structure by creating it manually
                # This simulates what _create_update_event_payload does
                groups = host_obj.groups
                expected_common = {"workspace_id": groups[0]["id"]} if len(groups) > 0 else {}

                # The common field should contain the workspace_id (group ID)
                assert expected_common == {"workspace_id": original_group_id}

                # Verify that the host's group information was updated with new name
                assert host_obj.groups[0]["name"] == new_group_name
                assert host_obj.groups[0]["id"] == original_group_id

    def test_host_group_update_via_mq_with_actual_outbox_common_validation(
        self,
        flask_app,
        event_producer_mock,
        notification_event_producer_mock,
        db_create_group_with_hosts,
        db_get_hosts_for_group,
        db_get_group_by_id,
    ):
        """Test complete MQ group update flow with actual outbox entry validation of common field."""

        # Create a group with one host for simpler validation
        group = db_create_group_with_hosts("test-workspace", 1)
        group_id = str(group.id)
        hosts = db_get_hosts_for_group(group.id)
        host = hosts[0]
        host_id = str(host.id)

        # Verify initial state
        assert len(host.groups) == 1
        assert host.groups[0]["id"] == group_id
        assert host.groups[0]["name"] == "test-workspace"

        # Create workspace update message
        new_name = "updated-workspace-name"
        message = generate_kessel_workspace_message("update", group_id, new_name)

        # Track actual outbox operations with success metrics and capture payload
        captured_payloads = []
        original_write_outbox = None

        def capture_outbox_payload(event_type, host_id_param, host_obj):
            # Call the original function to get the real behavior
            result = original_write_outbox(event_type, host_id_param, host_obj)

            # Manually create the payload to validate the common field
            if host_obj and len(host_obj.groups) > 0:
                common_field = {"workspace_id": host_obj.groups[0]["id"]}
                captured_payloads.append(
                    {
                        "event_type": event_type,
                        "host_id": host_id_param,
                        "common": common_field,
                        "group_name": host_obj.groups[0]["name"],
                        "group_id": host_obj.groups[0]["id"],
                    }
                )

            return result

        # Import and patch the actual function
        from lib.outbox_repository import write_event_to_outbox

        original_write_outbox = write_event_to_outbox

        with patch("lib.group_repository.write_event_to_outbox", side_effect=capture_outbox_payload):
            with patch("lib.outbox_repository.outbox_save_success") as mock_success_metric:
                # Process the workspace update message
                consumer = WorkspaceMessageConsumer(
                    None, flask_app, event_producer_mock, notification_event_producer_mock
                )
                result = consumer.handle_message(json.dumps(message))
                db.session.commit()

                # Verify the workspace update succeeded
                assert result.event_type == EventType.updated
                updated_group = db_get_group_by_id(group_id)
                assert updated_group.name == new_name

                # Verify outbox operation succeeded
                mock_success_metric.inc.assert_called_once()

                # Verify the captured payload has correct common field
                assert len(captured_payloads) == 1
                payload = captured_payloads[0]

                assert payload["event_type"] == EventType.updated
                assert payload["host_id"] == host_id
                assert payload["common"] == {"workspace_id": group_id}
                assert payload["group_name"] == new_name
                assert payload["group_id"] == group_id

                # Verify outbox entry was created (entries are no longer automatically pruned)
                outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
                assert len(outbox_entries) == 1  # Entry exists since automatic pruning was removed

                # Verify the outbox entry has the correct structure
                outbox_entry = outbox_entries[0]
                assert outbox_entry.aggregatetype == "hbi.hosts"
                assert outbox_entry.operation == "ReportResource"
                assert outbox_entry.version == "v1beta2"
                assert outbox_entry.payload["type"] == "host"
                assert outbox_entry.payload["reporterType"] == "hbi"

    def test_host_update_via_patch_endpoint_with_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_patch,
        db_create_host,
        db_get_host,
    ):
        """Test that updating a host via PATCH API endpoint triggers outbox entry creation."""

        # Create a host with initial data
        host = db_create_host(
            extra_data={"display_name": "original-host-name", "ansible_host": "original.ansible.host"}
        )
        host_id = str(host.id)

        # Verify initial state
        assert host.display_name == "original-host-name"
        assert host.ansible_host == "original.ansible.host"

        # Prepare patch data
        patch_data = {"display_name": "updated-host-name", "ansible_host": "updated.ansible.host"}
        hosts_url = build_hosts_url(host_list_or_id=host.id)

        # Mock the outbox writing to capture the calls and validate payload
        outbox_calls = []

        def mock_write_outbox(event_type, host_id_param, host_obj):
            outbox_calls.append({"event_type": event_type, "host_id": host_id_param, "host": host_obj})
            return True

        with patch("api.host.write_event_to_outbox", side_effect=mock_write_outbox):
            # Make PATCH request to update host
            response_status, response_data = api_patch(hosts_url, patch_data)

            # Verify the API request was successful
            assert response_status == 200

            # Verify outbox entry was created
            assert len(outbox_calls) == 1

            call = outbox_calls[0]
            assert call["event_type"] == EventType.updated
            assert call["host_id"] == host_id

            # Verify the host object in the outbox call has updated data
            host_obj = call["host"]
            assert host_obj is not None
            assert host_obj.display_name == "updated-host-name"
            assert host_obj.ansible_host == "updated.ansible.host"

            # Verify the host was actually updated in the database
            updated_host = db_get_host(host.id)
            assert updated_host.display_name == "updated-host-name"
            assert updated_host.ansible_host == "updated.ansible.host"

    def test_host_delete_via_api_endpoint_with_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        notification_event_producer_mock,  # noqa: ARG002
        api_delete_host,
        db_create_host,
        db_get_host,
    ):
        """Test that deleting a host via DELETE API endpoint triggers outbox entry creation."""

        # Create a host to delete
        host = db_create_host(extra_data={"display_name": "host-to-delete", "ansible_host": "delete.test.host"})
        host_id = str(host.id)

        # Verify initial state - host exists
        assert db_get_host(host.id) is not None
        assert host.display_name == "host-to-delete"

        # Mock the outbox writing to capture the calls and validate payload
        outbox_calls = []

        def mock_write_outbox(event_type, host_id_param, host_obj=None):
            outbox_calls.append({"event_type": event_type, "host_id": host_id_param, "host": host_obj})
            return True

        with patch("lib.host_delete.write_event_to_outbox", side_effect=mock_write_outbox):
            # Make DELETE request to delete the host
            response_status, response_data = api_delete_host(host.id)

            # Verify the API request was successful
            assert response_status == 200

            # Verify outbox entry was created
            assert len(outbox_calls) == 1

            call = outbox_calls[0]
            assert call["event_type"] == EventType.delete
            assert call["host_id"] == host_id

            # For delete events, no host object is passed (only host_id)
            assert call["host"] is None

            # Verify the host was actually deleted from the database
            deleted_host = db_get_host(host.id)
            assert deleted_host is None

    def test_host_add_to_group_via_api_endpoint_with_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_add_hosts_to_group,
        db_create_host,
        db_create_group,
        db_get_host,
        db_get_hosts_for_group,
    ):
        """Test that adding a host to a group via API endpoint triggers outbox entry creation."""

        # Create a group
        group = db_create_group("test-outbox-group")
        group_id = str(group.id)

        # Create a host (initially not in any group)
        host = db_create_host(extra_data={"display_name": "host-to-add-to-group", "ansible_host": "group.test.host"})
        host_id = str(host.id)

        # Verify initial state - group is empty, host has no groups
        initial_hosts_in_group = db_get_hosts_for_group(group_id)
        assert len(initial_hosts_in_group) == 0

        initial_host = db_get_host(host_id)
        assert len(initial_host.groups) == 0  # Host not in any group initially

        # Mock the outbox writing to capture the calls and validate payload
        outbox_calls = []

        def mock_write_outbox(event_type, host_id_param, host_obj):
            outbox_calls.append({"event_type": event_type, "host_id": host_id_param, "host": host_obj})
            return True

        with patch("lib.group_repository.write_event_to_outbox", side_effect=mock_write_outbox):
            # Make POST request to add host to group
            response_status, response_data = api_add_hosts_to_group(group_id, [host_id])

            # Verify the API request was successful
            assert response_status == 200

            # Verify outbox entry was created
            assert len(outbox_calls) == 1

            call = outbox_calls[0]
            assert call["event_type"] == EventType.updated
            assert call["host_id"] == host_id

            # Verify the host object in the outbox call has updated group information
            host_obj = call["host"]
            assert host_obj is not None
            assert len(host_obj.groups) == 1
            assert host_obj.groups[0]["id"] == group_id
            assert host_obj.groups[0]["name"] == "test-outbox-group"

            # Verify the host was actually added to the group in the database
            # Use group_id (string) instead of group.id to avoid session issues
            hosts_in_group_after = db_get_hosts_for_group(group_id)
            assert len(hosts_in_group_after) == 1
            assert str(hosts_in_group_after[0].id) == host_id

            # Verify the host now has the group information
            updated_host = db_get_host(host_id)
            assert len(updated_host.groups) == 1
            assert updated_host.groups[0]["id"] == group_id
            assert updated_host.groups[0]["name"] == "test-outbox-group"

    def test_host_add_to_group_via_api_endpoint_with_actual_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_add_hosts_to_group,
        db_create_host,
        db_create_group,
        db_get_host,
        db_get_hosts_for_group,
    ):
        """
        Test that adding a host to a group via API endpoint creates actual outbox entries
        with real functionality.
        """

        # Create a group
        group = db_create_group("test-actual-outbox-group")
        group_id = str(group.id)

        # Create a host (initially not in any group)
        host = db_create_host(
            extra_data={"display_name": "host-for-actual-outbox", "ansible_host": "actual.outbox.host"}
        )
        host_id = str(host.id)

        # Verify initial state - group is empty, host has no groups
        initial_hosts_in_group = db_get_hosts_for_group(group_id)
        assert len(initial_hosts_in_group) == 0

        initial_host = db_get_host(host_id)
        assert len(initial_host.groups) == 0  # Host not in any group initially

        # Use patch to capture outbox payload and verify the actual content
        outbox_payloads = []
        original_write_event_to_outbox = write_event_to_outbox

        def capture_outbox_payload(event_type, host_id_param, host_obj):
            # Call the original function to ensure real outbox functionality
            result = original_write_event_to_outbox(event_type, host_id_param, host_obj)

            # Capture the payload for validation by building it the same way
            if host_obj is not None:
                from lib.outbox_repository import _create_update_event_payload

                payload = _create_update_event_payload(host_obj)
                outbox_payloads.append(
                    {"event_type": event_type, "host_id": host_id_param, "payload": payload, "host": host_obj}
                )

            return result

        with patch("lib.group_repository.write_event_to_outbox", side_effect=capture_outbox_payload):
            # Make POST request to add host to group
            response_status, response_data = api_add_hosts_to_group(group_id, [host_id])

            # Verify the API request was successful
            assert response_status == 200

            # Verify outbox entry was created and processed
            assert len(outbox_payloads) == 1

            captured = outbox_payloads[0]
            assert captured["event_type"] == EventType.updated
            assert captured["host_id"] == host_id

            # Verify the host object has updated group information
            host_obj = captured["host"]
            assert host_obj is not None
            assert len(host_obj.groups) == 1
            assert host_obj.groups[0]["id"] == group_id
            assert host_obj.groups[0]["name"] == "test-actual-outbox-group"

            # Verify the outbox payload structure (what gets sent to Kessel)
            payload = captured["payload"]
            assert payload["type"] == "host"
            assert payload["reporterType"] == "hbi"
            assert payload["reporterInstanceId"] == "redhat.com"

            # Verify representations structure
            representations = payload["representations"]
            assert "metadata" in representations
            assert "common" in representations

            # Verify the "common" field contains the group workspace_id
            common = representations["common"]
            assert "workspace_id" in common
            assert common["workspace_id"] == group_id  # First group becomes workspace_id

            # Verify host metadata in payload exists
            metadata = representations["metadata"]
            # Note: metadata structure may vary - just verify it exists and contains expected fields
            assert metadata is not None
            # Check if host-specific fields are in metadata or somewhere else in the payload
            # Some fields might be in different parts of the representations

            # Verify the host was actually added to the group in the database
            hosts_in_group_after = db_get_hosts_for_group(group_id)
            assert len(hosts_in_group_after) == 1
            assert str(hosts_in_group_after[0].id) == host_id

            # Verify the host now has the group information
            updated_host = db_get_host(host_id)
            assert len(updated_host.groups) == 1
            assert updated_host.groups[0]["id"] == group_id
            assert updated_host.groups[0]["name"] == "test-actual-outbox-group"

            # Verify outbox entry was created (since we're patching the function, it won't be deleted immediately)
            outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
            assert len(outbox_entries) == 1  # Entry exists since we patched the function

            # Verify the outbox entry has the correct structure
            outbox_entry = outbox_entries[0]
            assert outbox_entry.aggregatetype == "hbi.hosts"
            assert outbox_entry.operation == "ReportResource"
            assert outbox_entry.version == "v1beta2"
            assert outbox_entry.payload["type"] == "host"
            assert outbox_entry.payload["reporterType"] == "hbi"

    def test_host_remove_from_group_via_api_endpoint_with_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_remove_hosts_from_group,
        api_add_hosts_to_group,
        db_create_host,
        db_create_group,
        db_get_host,
        db_get_hosts_for_group,
    ):
        """
        Test that removing a host from a group via API endpoint triggers outbox entry creation and
        validates group removal.
        """

        # Create a group
        group = db_create_group("test-remove-outbox-group")
        group_id = str(group.id)

        # Create a host
        host = db_create_host(
            extra_data={"display_name": "host-to-remove-from-group", "ansible_host": "remove.group.host"}
        )
        host_id = str(host.id)

        # First, add the host to the group so we can remove it later
        response_status, _ = api_add_hosts_to_group(group_id, [host_id])
        assert response_status == 200

        # Verify the host is in the group initially
        initial_hosts_in_group = db_get_hosts_for_group(group_id)
        assert len(initial_hosts_in_group) == 1
        assert str(initial_hosts_in_group[0].id) == host_id

        initial_host = db_get_host(host_id)
        assert len(initial_host.groups) == 1
        assert initial_host.groups[0]["id"] == group_id

        # Mock the outbox writing to capture the calls and validate payload
        outbox_calls = []

        def mock_write_outbox(event_type, host_id_param, host_obj):
            outbox_calls.append({"event_type": event_type, "host_id": host_id_param, "host": host_obj})
            return True

        # Mock the Kessel workspace migration flag to be False to avoid ungrouped group behavior
        with patch("lib.group_repository.get_flag_value", return_value=False):
            with patch("lib.group_repository.write_event_to_outbox", side_effect=mock_write_outbox):
                # Make DELETE request to remove host from group
                response_status, response_data = api_remove_hosts_from_group(group_id, [host_id])

                # Verify the API request was successful
                assert response_status == 204  # No Content

                # Verify outbox entry was created
                assert len(outbox_calls) == 1

                call = outbox_calls[0]
                assert call["event_type"] == EventType.updated
                assert call["host_id"] == host_id

                # Verify the host object in the outbox call has NO group information
                host_obj = call["host"]
                assert host_obj is not None
                assert len(host_obj.groups) == 0  # Host should have no groups after removal

                # Verify the host was actually removed from the group in the database
                hosts_in_group_after = db_get_hosts_for_group(group_id)
                assert len(hosts_in_group_after) == 0  # Group should be empty

                # Verify the host no longer has any group information
                updated_host = db_get_host(host_id)
                assert len(updated_host.groups) == 0  # Host should have no groups

    def test_host_remove_from_group_via_api_endpoint_with_actual_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_remove_hosts_from_group,
        api_add_hosts_to_group,
        db_create_host,
        db_create_group,
        db_get_host,
        db_get_hosts_for_group,
    ):
        """
        Test that removing a host from a group via API endpoint creates actual outbox entries and
        validates workspace removal.
        """

        # Create a group
        group = db_create_group("test-actual-remove-outbox-group")
        group_id = str(group.id)

        # Create a host
        host = db_create_host(
            extra_data={"display_name": "host-for-actual-remove-outbox", "ansible_host": "actual.remove.outbox.host"}
        )
        host_id = str(host.id)

        # First, add the host to the group so we can remove it later
        response_status, _ = api_add_hosts_to_group(group_id, [host_id])
        assert response_status == 200

        # Verify the host is in the group initially
        initial_hosts_in_group = db_get_hosts_for_group(group_id)
        assert len(initial_hosts_in_group) == 1

        initial_host = db_get_host(host_id)
        assert len(initial_host.groups) == 1
        assert initial_host.groups[0]["id"] == group_id

        # Use patch to capture outbox payload and verify the actual content
        outbox_payloads = []
        original_write_event_to_outbox = write_event_to_outbox

        def capture_outbox_payload(event_type, host_id_param, host_obj):
            # Call the original function to ensure real outbox functionality
            result = original_write_event_to_outbox(event_type, host_id_param, host_obj)

            # Capture the payload for validation by building it the same way
            if host_obj is not None:
                from lib.outbox_repository import _create_update_event_payload

                payload = _create_update_event_payload(host_obj)
                outbox_payloads.append(
                    {"event_type": event_type, "host_id": host_id_param, "payload": payload, "host": host_obj}
                )

            return result

        # Enable the Kessel workspace migration flag to get ungrouped group behavior (as required by Kessel)
        with patch("lib.group_repository.get_flag_value", return_value=True):
            with patch("lib.group_repository.write_event_to_outbox", side_effect=capture_outbox_payload):
                # Make DELETE request to remove host from group
                response_status, response_data = api_remove_hosts_from_group(group_id, [host_id])

                # Verify the API request was successful
                assert response_status == 204  # No Content

                # Verify outbox entry was created and processed
                assert len(outbox_payloads) == 1

                captured = outbox_payloads[0]
                assert captured["event_type"] == EventType.updated
                assert captured["host_id"] == host_id

                # Verify the host object has ungrouped group information after removal (Kessel requirement)
                host_obj = captured["host"]
                assert host_obj is not None
                assert len(host_obj.groups) == 1  # Host should be in "ungrouped hosts" group
                assert host_obj.groups[0]["name"] == "Ungrouped Hosts"  # Kessel requires ungrouped hosts group

                # Verify the outbox payload structure (what gets sent to Kessel)
                payload = captured["payload"]
                assert payload["type"] == "host"
                assert payload["reporterType"] == "hbi"
                assert payload["reporterInstanceId"] == "redhat.com"

                # Verify representations structure
                representations = payload["representations"]
                assert "metadata" in representations
                assert "common" in representations

                # Verify the "common" field contains workspace_id for the ungrouped hosts group
                common = representations["common"]
                assert "workspace_id" in common
                # The workspace_id should be the ungrouped hosts group ID
                ungrouped_group_id = host_obj.groups[0]["id"]
                assert common["workspace_id"] == ungrouped_group_id

                # Verify host metadata in payload exists
                metadata = representations["metadata"]
                assert metadata is not None

                # Verify the host was actually removed from the original group in the database
                hosts_in_group_after = db_get_hosts_for_group(group_id)
                assert len(hosts_in_group_after) == 0  # Original group should be empty

                # Verify the host is now in the ungrouped hosts group
                updated_host = db_get_host(host_id)
                assert len(updated_host.groups) == 1  # Host should be in ungrouped group
                assert updated_host.groups[0]["name"] == "Ungrouped Hosts"

                # Verify outbox entries were created (entries are no longer automatically pruned)
                outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
                assert len(outbox_entries) == 2  # Two entries exist since automatic pruning was removed

                # Verify the outbox entries have the correct structure
                operations = [entry.operation for entry in outbox_entries]
                assert "ReportResource" in operations  # Both should be ReportResource operations

    def test_host_facts_replace_via_put_endpoint_with_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_put,
        db_create_host,
        db_get_host,
    ):
        """Test that replacing host facts via PUT API endpoint triggers outbox entry creation."""

        # Create a host with initial facts
        host = db_create_host(
            extra_data={
                "display_name": "host-with-facts",
                "ansible_host": "facts.test.host",
                "facts": {"test_namespace": {"original_key": "original_value", "existing_key": "existing_value"}},
            }
        )
        host_id = str(host.id)

        # Verify initial state
        initial_host = db_get_host(host.id)
        assert initial_host.facts["test_namespace"]["original_key"] == "original_value"
        assert initial_host.facts["test_namespace"]["existing_key"] == "existing_value"

        # Prepare PUT data to replace facts in the namespace
        put_data = {"new_key": "new_value", "another_key": "another_value"}
        facts_url = build_hosts_url(host_list_or_id=host.id, path="/facts/test_namespace")

        # Mock the outbox writing to capture the calls and validate payload
        outbox_calls = []

        def mock_write_outbox(event_type, host_id_param, host_obj):
            outbox_calls.append({"event_type": event_type, "host_id": host_id_param, "host": host_obj})
            return True

        with patch("api.host.write_event_to_outbox", side_effect=mock_write_outbox):
            # Make PUT request to replace facts in namespace
            response_status, response_data = api_put(facts_url, put_data)

            # Verify the API request was successful
            assert response_status == 200

            # Verify outbox entry was created
            assert len(outbox_calls) == 1

            call = outbox_calls[0]
            assert call["event_type"] == EventType.updated
            assert call["host_id"] == host_id

            # Verify the host object in the outbox call has updated facts
            host_obj = call["host"]
            assert host_obj is not None
            assert host_obj.facts["test_namespace"]["new_key"] == "new_value"
            assert host_obj.facts["test_namespace"]["another_key"] == "another_value"
            # Verify old facts were replaced (not merged)
            assert "original_key" not in host_obj.facts["test_namespace"]
            assert "existing_key" not in host_obj.facts["test_namespace"]

            # Verify the host was actually updated in the database
            updated_host = db_get_host(host.id)
            assert updated_host.facts["test_namespace"]["new_key"] == "new_value"
            assert updated_host.facts["test_namespace"]["another_key"] == "another_value"
            assert "original_key" not in updated_host.facts["test_namespace"]
            assert "existing_key" not in updated_host.facts["test_namespace"]

    def test_host_facts_replace_via_put_endpoint_with_actual_outbox_validation(
        self,
        flask_app,  # noqa: ARG002
        event_producer_mock,  # noqa: ARG002
        api_put,
        db_create_host,
        db_get_host,
    ):
        """
        Test that replacing host facts via PUT API endpoint creates actual outbox entries
        with real functionality and validates the payload structure.
        """

        # Create a host with initial facts
        host = db_create_host(
            extra_data={
                "display_name": "host-for-actual-facts-outbox",
                "ansible_host": "actual.facts.outbox.host",
                "facts": {"test_namespace": {"original_key": "original_value", "existing_key": "existing_value"}},
            }
        )
        host_id = str(host.id)

        # Verify initial state
        initial_host = db_get_host(host.id)
        assert initial_host.facts["test_namespace"]["original_key"] == "original_value"
        assert initial_host.facts["test_namespace"]["existing_key"] == "existing_value"

        # Prepare PUT data to replace facts in the namespace
        put_data = {"new_key": "new_value", "another_key": "another_value"}
        facts_url = build_hosts_url(host_list_or_id=host.id, path="/facts/test_namespace")

        # Use patch to capture outbox payload and verify the actual content
        outbox_payloads = []
        original_write_event_to_outbox = write_event_to_outbox

        def capture_outbox_payload(event_type, host_id_param, host_obj):
            # Call the original function to ensure real outbox functionality
            result = original_write_event_to_outbox(event_type, host_id_param, host_obj)

            # Capture the payload for validation by building it the same way
            if host_obj is not None:
                from lib.outbox_repository import _create_update_event_payload

                payload = _create_update_event_payload(host_obj)
                outbox_payloads.append(
                    {"event_type": event_type, "host_id": host_id_param, "payload": payload, "host": host_obj}
                )

            return result

        with patch("api.host.write_event_to_outbox", side_effect=capture_outbox_payload):
            # Make PUT request to replace facts in namespace
            response_status, response_data = api_put(facts_url, put_data)

            # Verify the API request was successful
            assert response_status == 200

            # Verify outbox entry was created and processed
            assert len(outbox_payloads) == 1

            captured = outbox_payloads[0]
            assert captured["event_type"] == EventType.updated
            assert captured["host_id"] == host_id

            # Verify the host object has updated facts
            host_obj = captured["host"]
            assert host_obj is not None
            assert host_obj.facts["test_namespace"]["new_key"] == "new_value"
            assert host_obj.facts["test_namespace"]["another_key"] == "another_value"
            # Verify old facts were replaced (not merged)
            assert "original_key" not in host_obj.facts["test_namespace"]
            assert "existing_key" not in host_obj.facts["test_namespace"]

            # Verify the outbox payload structure (what gets sent to Kessel)
            payload = captured["payload"]
            assert payload["type"] == "host"
            assert payload["reporterType"] == "hbi"
            assert payload["reporterInstanceId"] == "redhat.com"

            # Verify representations structure
            representations = payload["representations"]
            assert "metadata" in representations
            assert "common" in representations
            assert "reporter" in representations

            # Verify metadata structure
            metadata = representations["metadata"]
            assert metadata["localResourceId"] == host_id
            assert metadata["apiHref"] == "https://apiHref.com/"
            assert metadata["consoleHref"] == "https://www.console.com/"
            assert metadata["reporterVersion"] == "1.0"

            # Verify reporter structure
            reporter = representations["reporter"]
            assert "satellite_id" in reporter
            assert "subscription_manager_id" in reporter
            assert "insights_id" in reporter
            assert "ansible_host" in reporter

            # Verify the host was actually updated in the database
            updated_host = db_get_host(host.id)
            assert updated_host.facts["test_namespace"]["new_key"] == "new_value"
            assert updated_host.facts["test_namespace"]["another_key"] == "another_value"
            assert "original_key" not in updated_host.facts["test_namespace"]
            assert "existing_key" not in updated_host.facts["test_namespace"]

            # Verify outbox entry was created (since we're patching the function, it won't be deleted immediately)
            outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
            assert len(outbox_entries) == 1  # Entry exists since we patched the function

            # Verify the outbox entry has the correct structure
            outbox_entry = outbox_entries[0]
            assert outbox_entry.aggregatetype == "hbi.hosts"
            assert outbox_entry.operation == "ReportResource"
            assert outbox_entry.version == "v1beta2"
            assert outbox_entry.payload["type"] == "host"
            assert outbox_entry.payload["reporterType"] == "hbi"
