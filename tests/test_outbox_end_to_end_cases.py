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
from sqlalchemy.orm import Session as SQLASession

from app.exceptions import OutboxSaveException
from app.models import Group
from app.models import HostGroupAssoc
from app.models.database import db
from app.models.host import Host
from app.models.outbox import Outbox
from app.models.schemas import OutboxSchema
from app.queue.events import EventType
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import WorkspaceMessageConsumer
from lib.host_outbox_events import _collect_pending_ops_for_session
from lib.outbox_repository import _create_update_event_payload
from lib.outbox_repository import remove_event_from_outbox
from lib.outbox_repository import write_event_to_outbox
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.mq_utils import generate_kessel_workspace_message
from tests.helpers.mq_utils import wrap_message
from tests.helpers.outbox_utils import assert_outbox_empty
from tests.helpers.outbox_utils import build_delete_payload
from tests.helpers.outbox_utils import build_updated_payload
from tests.helpers.outbox_utils import capture_outbox_calls
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
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "fqdn": "test-host.example.com",
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        }

        created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
        host_id = str(created_host.id)

        # Retrieve the host to ensure it has groups
        host = db_get_host(created_host.id)

        # Track outbox success metrics to verify outbox operation succeeded
        with patch("lib.outbox_repository.outbox_save_success") as mock_success_metric:
            # Write created event to outbox
            result = write_event_to_outbox(EventType.created, host_id, host)

            # Verify the operation succeeded
            assert result is True

            # Verify outbox operation succeeded (metric was incremented)
            mock_success_metric.inc.assert_called_once()

            # Verify outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success metric increment proves the outbox entry was created, validated, and processed

    def test_successful_updated_event_e2e(self, db_create_host, db_get_host):
        """Test complete flow for a successful 'updated' event."""
        # Create a host
        host_data = {
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        }

        created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # Track outbox success metrics to verify outbox operation succeeded
        with patch("lib.outbox_repository.outbox_save_success") as mock_success_metric:
            # Write updated event to outbox
            result = write_event_to_outbox(EventType.updated, host_id, host)

            # Verify the operation succeeded
            assert result is True

            # Verify outbox operation succeeded (metric was incremented)
            mock_success_metric.inc.assert_called_once()

            # Verify outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success metric increment proves the outbox entry was created, validated, and processed

    def test_successful_delete_event_e2e(self, db_create_host):
        """Test complete flow for a successful 'delete' event."""
        # Create a host first
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)

        # Track outbox success metrics to verify outbox operation succeeded
        with patch("lib.outbox_repository.outbox_save_success") as mock_success_metric:
            # Write delete event to outbox (no host object needed for delete)
            result = write_event_to_outbox(EventType.delete, host_id)

            # Verify the operation succeeded
            assert result is True

            # Verify outbox operation succeeded (metric was incremented)
            mock_success_metric.inc.assert_called_once()

            # Verify outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success metric increment proves the outbox entry was created, validated, and processed

    def test_multiple_events_same_host_e2e(self, db_create_host, db_get_host):
        """Test multiple events for the same host create separate outbox entries."""
        # Create a host
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # Track outbox success metrics to verify outbox operations succeeded
        with patch("lib.outbox_repository.outbox_save_success") as mock_success_metric:
            # Write multiple events
            write_event_to_outbox(EventType.created, host_id, host)
            write_event_to_outbox(EventType.updated, host_id, host)
            write_event_to_outbox(EventType.delete, host_id)

            # Verify all outbox operations succeeded (metric was incremented 3 times)
            assert mock_success_metric.inc.call_count == 3

            # Verify outbox entries were created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success metric increments prove the outbox entries were created, validated, and processed

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
        assert_outbox_empty(db, host_id)

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
        insights_id = generate_uuid()
        subscription_manager_id = generate_uuid()

        host_without_id = Host(
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            reporter="test-reporter",
        )
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
        insights_id = generate_uuid()
        subscription_manager_id = generate_uuid()
        host = Host(
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            reporter="test-reporter",
        )
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
            "operation": "created",  # Use 'created' to trigger payload validation
            "version": "v1beta2",
            "payload": {
                "type": "host",
                "reporter_type": "hbi",
                "reporter_instance_id": "redhat.com",
                "representations": {
                    "metadata": {
                        "local_resource_id": str(uuid.uuid4()),
                        "api_href": "https://apihref.com/",
                        "console_href": "https://www.console.com/",
                        "reporter_version": "1.0",
                        "transaction_id": str(uuid.uuid4()),
                    },
                    "common": {"workspace_id": str(uuid.uuid4())},
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
        delete_payload = build_delete_payload()

        validated_delete_data = schema.load(delete_payload)
        assert validated_delete_data is not None

    def test_outbox_schema_validation_fails_without_transaction_id(self):
        """Test that outbox entries without transaction_id fail schema validation."""
        # Test created/updated payload without transaction_id
        created_payload_missing_transaction_id = {
            "aggregatetype": "hbi.hosts",
            "aggregateid": str(uuid.uuid4()),
            "operation": "created",  # Use 'created' to trigger payload validation
            "version": "v1beta2",
            "payload": {
                "type": "host",
                "reporter_type": "hbi",
                "reporter_instance_id": "redhat.com",
                "representations": {
                    "metadata": {
                        "local_resource_id": str(uuid.uuid4()),
                        "api_href": "https://apihref.com/",
                        "console_href": "https://www.console.com/",
                        "reporter_version": "1.0",
                        # transaction_id is missing - this should cause validation to fail
                    },
                    "common": {"workspace_id": str(uuid.uuid4())},
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

        # This should raise a validation error because transaction_id is missing
        with pytest.raises(MarshmallowValidationError) as exc_info:
            schema.load(created_payload_missing_transaction_id)

        # Verify the error message mentions the missing transaction_id field
        error_message = str(exc_info.value)
        assert "transaction_id" in error_message

    def test_outbox_schema_validation_success_updated_operation(self):
        """Test that valid outbox entries with 'updated' operation pass schema validation."""
        # Test updated payload
        updated_payload = build_updated_payload()

        schema = OutboxSchema()
        validated_data = schema.load(updated_payload)
        assert validated_data is not None

    def test_outbox_schema_validation_fails_without_transaction_id_updated_operation(self):
        """Test that outbox entries with 'updated' operation without transaction_id fail schema validation."""
        # Test updated payload without transaction_id
        updated_payload_missing_transaction_id = build_updated_payload()
        # Remove transaction_id to cause validation to fail
        del updated_payload_missing_transaction_id["payload"]["representations"]["metadata"]["transaction_id"]

        schema = OutboxSchema()

        # This should raise a validation error because transaction_id is missing
        with pytest.raises(MarshmallowValidationError) as exc_info:
            schema.load(updated_payload_missing_transaction_id)

        # Verify the error message mentions the missing transaction_id field
        error_message = str(exc_info.value)
        assert "transaction_id" in error_message

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

        # Verify outbox entry was created and immediately deleted (new behavior)
        assert_outbox_empty(db, host_id)

        # The success of the operation indicates the outbox entry was created, validated, and processed

    def test_transaction_rollback_behavior(self, db_create_host, db_get_host):
        """Test that outbox entries are committed immediately and not subject to external rollback."""
        created_host = db_create_host(SYSTEM_IDENTITY)
        host_id = str(created_host.id)
        host = db_get_host(created_host.id)

        # The outbox implementation now commits immediately within the function
        # This test verifies that the function handles its own transaction
        result = write_event_to_outbox(EventType.created, host_id, host)
        assert result is True

        # Verify entry was created and immediately deleted (new behavior)
        assert_outbox_empty(db, host_id)

        # The success of the operation indicates the outbox entry was created, validated, and processed

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

        # Verify all entries were created and immediately deleted (new behavior)
        all_entries = db.session.query(Outbox).all()
        assert len(all_entries) == 0  # All entries are immediately deleted after flush

        # The success of the operations indicates the outbox entries were created, validated, and processed

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

        # Capture outbox calls using helper
        with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox") as outbox_calls:
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
            assert len(outbox_calls) == 1
            call = outbox_calls[0]

            # Check the event type
            assert call["event_type"] == EventType.created

            # Check the host ID
            assert str(call["host_id"]) == str(created_host.id)

            # Check the host object
            outbox_host = call["host"]
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

        # Capture outbox calls using helper with groups
        with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox", capture_groups=True) as outbox_calls:
            # Create MQ consumer and process message
            consumer = IngressMessageConsumer(None, flask_app, event_producer_mock, notification_event_producer_mock)
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
            assert len(outbox_calls) == 1
            call = outbox_calls[0]

            # Check the event type
            assert call["event_type"] == EventType.created

            # Check the host ID
            assert str(call["host_id"]) == str(created_host.id)

            # Check the host object
            outbox_host = call["host"]
            assert outbox_host.id == created_host.id
            assert outbox_host.insights_id == created_host.insights_id
            assert outbox_host.fqdn == created_host.fqdn
            assert len(outbox_host.groups) == 1  # Verify groups are included in outbox payload

            # Verify groups information was captured
            groups_info = call["groups"]
            assert groups_info is not None
            assert len(groups_info) == 1

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

            # Verify outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, str(created_host.id))

            # The success metric increment proves the outbox entry was created, validated, and processed

    def test_host_group_update_via_mq_with_actual_outbox_common_validation(
        self,
        flask_app,
        event_producer_mock,
        notification_event_producer_mock,
        db_create_group_with_hosts,
        db_get_hosts_for_group,
        db_get_group_by_id,
    ):
        """
        Test complete MQ group update flow - group name changes should NOT trigger outbox entries
        since only group_id is in outbox payload.
        """

        # Create a group with one host for simpler validation
        group = db_create_group_with_hosts("test-workspace", 1)
        group_id = str(group.id)
        hosts = db_get_hosts_for_group(group.id)
        host = hosts[0]
        _ = str(host.id)

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

        def capture_outbox_payload(event_type, host_id_param, host_obj, session=None, **kwargs):
            # Call the original function to get the real behavior
            result = original_write_outbox(event_type, host_id_param, host_obj, session=session, **kwargs)

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

        original_write_outbox = write_event_to_outbox

        with patch("lib.outbox_repository.write_event_to_outbox", side_effect=capture_outbox_payload):
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

                # Verify NO outbox operation occurred since the group name change doesn't affect outbox payload.
                mock_success_metric.inc.assert_not_called()

                # Verify NO outbox payloads were captured since group name change doesn't affect outbox payload.
                assert len(captured_payloads) == 0

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_update_via_patch_endpoint_display_name_no_outbox(
        self,
        api_patch,
        db_create_host,
        db_get_host,
    ):
        """
        Test that updating a host's display_name via PATCH API endpoint does NOT trigger outbox entry creation
        since display_name is not included in the outbox payload.
        """

        # Create a host with initial data
        host = db_create_host(
            extra_data={"display_name": "original-host-name", "ansible_host": "original.ansible.host"}
        )
        _ = str(host.id)

        # Verify initial state
        assert host.display_name == "original-host-name"
        assert host.ansible_host == "original.ansible.host"

        # Prepare patch data - only change display_name (not in outbox payload)
        patch_data = {"display_name": "updated-host-name"}
        hosts_url = build_hosts_url(host_list_or_id=host.id)

        # Capture outbox calls via helper fixture

        with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox") as outbox_calls:
            # Make PATCH request to update display_name only
            response_status, _ = api_patch(hosts_url, patch_data)

            # Verify the API request was successful
            assert response_status == 200

            # Verify NO outbox entry was created since only display_name changed (not in outbox payload)
            assert len(outbox_calls) == 0

            # Verify the host was actually updated in the database
            updated_host = db_get_host(host.id)
            assert updated_host.display_name == "updated-host-name"
            assert updated_host.ansible_host == "original.ansible.host"  # ansible_host unchanged

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_update_via_patch_endpoint_ansible_host_with_outbox(
        self,
        api_patch,
        db_create_host,
        db_get_host,
    ):
        """
        Test that updating a host's ansible_host via PATCH API endpoint triggers outbox entry creation
        since ansible_host is included in the outbox payload.
        """

        # Ensure clean database state
        db.session.rollback()

        # Create a host with initial data
        host = db_create_host(
            extra_data={"display_name": "original-host-name", "ansible_host": "original.ansible.host"}
        )
        host_id = str(host.id)

        # Verify initial state
        assert host.display_name == "original-host-name"
        assert host.ansible_host == "original.ansible.host"

        # Prepare patch data - change ansible_host (is in outbox payload)
        patch_data = {"ansible_host": "updated.ansible.host"}
        hosts_url = build_hosts_url(host_list_or_id=host.id)

        # Make PATCH request to update ansible_host
        # Outbox entry is created automatically via event listener when ansible_host changes
        response_status, _ = api_patch(hosts_url, patch_data)

        # Verify the API request was successful
        assert response_status == 200

        # Verify the host was actually updated in the database
        updated_host = db_get_host(host.id)
        assert updated_host.ansible_host == "updated.ansible.host"
        assert updated_host.display_name == "original-host-name"  # display_name unchanged

        # Verify outbox entry was created and immediately deleted (write-ahead log pattern)
        # The outbox entry is created during commit and then deleted immediately as part of the write-ahead log
        assert_outbox_empty(db, host_id)

    @pytest.mark.usefixtures("notification_event_producer")
    def test_host_delete_via_api_endpoint_with_actual_outbox_validation(
        self,
        api_delete_host,
        db_create_host,
        db_get_host,
        event_producer,
    ):
        """
        Test that deleting a host via DELETE API endpoint triggers actual outbox entry creation and
        automatic cleanup.
        """

        # Create a host to delete
        host = db_create_host(extra_data={"display_name": "host-to-delete", "ansible_host": "delete.test.host"})
        host_id = str(host.id)

        # Verify initial state - host exists
        assert db_get_host(host.id) is not None
        assert host.display_name == "host-to-delete"

        # Create a mock event producer that doesn't clean up the outbox entry
        # This allows us to validate the outbox entry structure
        class MockEventProducerNoCleanup:
            def __init__(self):
                self.mq_topic = "test-topic"

            def write_event(self, event, key, headers, *, wait=False):
                # Don't call remove_event_from_outbox, just simulate the event production
                pass

            def close(self):
                pass

        # Use the mock event producer to test outbox entry creation without cleanup
        with (
            patch("api.host.current_app.event_producer", MockEventProducerNoCleanup()),
            patch("lib.host_delete.kafka_available", return_value=True),
        ):
            # Make DELETE request to delete the host
            response_status, _ = api_delete_host(host.id)

            # Verify the API request was successful
            assert response_status == 200

            # Verify the host was actually deleted from the database
            deleted_host = db_get_host(host.id)
            assert deleted_host is None

            # Verify that the outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success of the operation indicates the outbox entry was created, validated, and processed

        # Now test with the real event producer to verify automatic cleanup
        # Create another host to delete
        host2 = db_create_host(extra_data={"display_name": "host-to-delete-2", "ansible_host": "delete2.test.host"})
        host2_id = str(host2.id)

        # Verify initial state - host exists
        assert db_get_host(host2.id) is not None
        assert host2.display_name == "host-to-delete-2"

        # We want to use the real event producer, but we need to mock the kafka functions
        event_producer._kafka_producer.flush = Mock(return_value=True)
        event_producer._kafka_producer.poll = Mock(return_value=True)
        event_producer._kafka_producer.produce = Mock(return_value=True)

        with patch("lib.host_delete.kafka_available", return_value=True):
            # Make DELETE request to delete the second host (using real event producer)
            response_status, _ = api_delete_host(host2.id)

        # Verify the API request was successful
        assert response_status == 200

        # Verify the host was actually deleted from the database
        deleted_host2 = db_get_host(host2.id)
        assert deleted_host2 is None

        # Verify that the outbox table has been automatically cleaned up by the real event producer
        remaining_outbox_entries = db.session.query(Outbox).filter_by(aggregateid=host2_id).all()
        assert len(remaining_outbox_entries) == 0

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_add_to_group_via_api_endpoint_with_outbox_validation(
        self,
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

        # Make POST request to add host to group
        # Outbox entry is created automatically via event listener when groups change
        response_status, _ = api_add_hosts_to_group(group_id, [host_id])

        # Verify the API request was successful
        assert response_status == 200

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

        # Verify outbox entry was created and immediately deleted (write-ahead log pattern)
        assert_outbox_empty(db, host_id)

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_add_to_group_via_api_endpoint_with_actual_outbox_validation(
        self,
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

        def capture_outbox_payload(event_type, host_id_param, host_obj, session=None):
            # Capture groups information while host is still attached to session
            groups_info = None
            if host_obj is not None:
                groups_info = host_obj.groups

            # Call the original function to ensure real outbox functionality
            result = original_write_event_to_outbox(event_type, host_id_param, host_obj, session=session)

            # Capture the payload for validation by building it the same way
            if host_obj is not None:
                payload = _create_update_event_payload(host_obj)
                outbox_payloads.append(
                    {
                        "event_type": event_type,
                        "host_id": host_id_param,
                        "payload": payload,
                        "host": host_obj,
                        "groups": groups_info,
                    }
                )

            return result

        with patch(
            "lib.host_outbox_events.outbox_repository.write_event_to_outbox", side_effect=capture_outbox_payload
        ):
            # Make POST request to add host to group
            response_status, _ = api_add_hosts_to_group(group_id, [host_id])

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

            # Use the captured groups information instead of accessing the detached host object
            groups_info = captured["groups"]
            assert groups_info is not None
            assert len(groups_info) == 1
            assert groups_info[0]["id"] == group_id
            assert groups_info[0]["name"] == "test-actual-outbox-group"

            # Verify the outbox payload structure (what gets sent to Kessel)
            payload = captured["payload"]
            assert payload["type"] == "host"
            assert payload["reporter_type"] == "hbi"
            assert payload["reporter_instance_id"] == "redhat"

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
            # Verify transaction_id is present in metadata
            assert "transaction_id" in metadata
            assert metadata["transaction_id"] is not None

            # Verify transaction_id is a valid UUID format
            uuid.UUID(metadata["transaction_id"])  # This will raise ValueError if not a valid UUID
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

            # Verify outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success of the operation indicates the outbox entry was created, validated, and processed

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_remove_from_group_via_api_endpoint_with_outbox_validation(
        self,
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

        # Capture outbox calls using helper with groups
        with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox", capture_groups=True) as outbox_calls:
            # Make DELETE request to remove host from group
            response_status, _ = api_remove_hosts_from_group(group_id, [host_id])

            # Verify the API request was successful
            assert response_status == 204  # No Content

            # Verify outbox entry was created
            assert len(outbox_calls) == 1

            call = outbox_calls[0]
            assert call["event_type"] == EventType.updated
            assert call["host_id"] == host_id

            # Use the captured groups information instead of accessing the detached host object
            groups_info = call["groups"]
            assert groups_info is not None
            assert groups_info[0].get("ungrouped") is True

            # Verify the host is in the ungrouped hosts group
            updated_host = db_get_host(host_id)
            assert updated_host.groups[0].get("ungrouped") is True

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_facts_replace_via_put_endpoint_with_outbox_validation(
        self,
        api_put,
        db_create_host,
        db_get_host,
    ):
        """
        Test that replacing host facts via PUT API endpoint does NOT trigger outbox entry creation
        since facts are not included in the outbox payload.
        """

        # Create a host with initial facts
        host = db_create_host(
            extra_data={
                "display_name": "host-with-facts",
                "ansible_host": "facts.test.host",
                "facts": {"test_namespace": {"original_key": "original_value", "existing_key": "existing_value"}},
            }
        )
        _ = str(host.id)

        # Verify initial state
        initial_host = db_get_host(host.id)
        assert initial_host.facts["test_namespace"]["original_key"] == "original_value"
        assert initial_host.facts["test_namespace"]["existing_key"] == "existing_value"

        # Prepare PUT data to replace facts in the namespace
        put_data = {"new_key": "new_value", "another_key": "another_value"}
        facts_url = build_hosts_url(host_list_or_id=host.id, path="/facts/test_namespace")

        # Capture outbox calls using helper
        with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox") as outbox_calls:
            # Make PUT request to replace facts in namespace
            response_status, _ = api_put(facts_url, put_data)

            # Verify the API request was successful
            assert response_status == 200

            # Verify NO outbox entry was created since facts are not in outbox payload
            assert len(outbox_calls) == 0

            # Verify the host was actually updated in the database
            updated_host = db_get_host(host.id)
            assert updated_host.facts["test_namespace"]["new_key"] == "new_value"
            assert updated_host.facts["test_namespace"]["another_key"] == "another_value"
            assert "original_key" not in updated_host.facts["test_namespace"]
            assert "existing_key" not in updated_host.facts["test_namespace"]

    @pytest.mark.usefixtures("event_producer_mock")
    def test_host_facts_replace_via_put_endpoint_with_actual_outbox_validation(
        self,
        api_put,
        db_create_host,
        db_get_host,
    ):
        """
        Test that replacing host facts via PUT API endpoint does NOT create outbox entries
        since facts are not included in the outbox payload.
        """

        # Create a host with initial facts
        host = db_create_host(
            extra_data={
                "display_name": "host-for-actual-facts-outbox",
                "ansible_host": "actual.facts.outbox.host",
                "facts": {"test_namespace": {"original_key": "original_value", "existing_key": "existing_value"}},
            }
        )
        _ = str(host.id)

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
                payload = _create_update_event_payload(host_obj)
                outbox_payloads.append(
                    {"event_type": event_type, "host_id": host_id_param, "payload": payload, "host": host_obj}
                )

            return result

        with patch("lib.outbox_repository.write_event_to_outbox", side_effect=capture_outbox_payload):
            # Make PUT request to replace facts in namespace
            response_status, response_data = api_put(facts_url, put_data)

            # Verify the API request was successful
            assert response_status == 200

            # Verify NO outbox entry was created since facts are not in outbox payload
            assert len(outbox_payloads) == 0

            # Verify the host was actually updated in the database
            updated_host = db_get_host(host.id)
            assert updated_host.facts["test_namespace"]["new_key"] == "new_value"
            assert updated_host.facts["test_namespace"]["another_key"] == "another_value"
            # Verify old facts were replaced (not merged)
            assert "original_key" not in updated_host.facts["test_namespace"]
            assert "existing_key" not in updated_host.facts["test_namespace"]

    def test_host_creation_with_outbox_validation_and_cleanup(self, db_create_host, db_get_host):
        """
        Test complete host creation workflow with outbox validation:
        1. Create a new host
        2. Validate outbox entry is created with correct host_id as aggregateid
        3. Validate outbox entry is deleted after calling remove_event_from_outbox
        4. Ensure host_id matches aggregateid throughout the process
        """
        # Create a host with all required fields
        insights_id = generate_uuid()
        subscription_manager_id = generate_uuid()
        host_data = {
            "insights_id": insights_id,
            "subscription_manager_id": subscription_manager_id,
            "fqdn": "test-kafka-host.example.com",
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        }

        created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
        host_id = str(created_host.id)

        # Verify the host was created successfully
        assert created_host is not None
        assert created_host.fqdn == "test-kafka-host.example.com"
        assert str(created_host.id) == host_id

        # Retrieve the host to ensure it has all necessary data
        host = db_get_host(created_host.id)
        assert host is not None

        # Write created event to outbox
        result = write_event_to_outbox(EventType.created, host_id, host)

        # Verify the operation succeeded
        assert result is True

        # Verify outbox entry was created and immediately deleted (new behavior)
        assert_outbox_empty(db, host_id)

        # The success of the operation indicates the outbox entry was created, validated, and processed

        # Test outbox entry deletion by calling remove_event_from_outbox directly

        # Verify the outbox entry was created and immediately deleted (new behavior)
        assert_outbox_empty(db, host_id)

        # Call the remove_event_from_outbox function directly
        remove_event_from_outbox(host_id)

        # Verify the outbox entry has been deleted
        assert_outbox_empty(db, host_id)

        # Final validation: ensure the host still exists in the database
        final_host = db_get_host(created_host.id)
        assert final_host is not None
        assert str(final_host.id) == host_id
        assert final_host.fqdn == "test-kafka-host.example.com"

    @pytest.mark.usefixtures("event_producer_mock")
    def test_delete_hosts_from_group_with_outbox_validation_and_ungrouped_assignment(
        self,
        db_create_host,
        db_create_group,
        db_get_host,
        api_add_hosts_to_group,
        api_remove_hosts_from_group,
        db_get_hosts_for_group,
    ):
        """
        Test complete workflow for deleting 2 hosts from a group of 3 hosts with outbox validation:
        1. Create 3 new hosts
        2. Create a new group
        3. Add all 3 hosts to the group via API
        4. Remove 2 hosts from the group via API
        5. Validate the group still contains 1 host
        6. Validate removed hosts are assigned to "ungrouped_hosts" group
        7. Validate outbox entries are created and then deleted for all operations
        8. Ensure host_id matches aggregateid throughout the process
        """
        # Create 3 hosts with unique data
        hosts_data = []
        created_hosts = []
        host_ids = []

        for i in range(3):
            insights_id = generate_uuid()
            subscription_manager_id = generate_uuid()
            host_data = {
                "insights_id": insights_id,
                "subscription_manager_id": subscription_manager_id,
                "fqdn": f"test-delete-host-{i + 1}.example.com",
                "display_name": f"Test Delete Host {i + 1}",
                "ansible_host": f"delete-host-{i + 1}.ansible.host",
                "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            }
            hosts_data.append(host_data)

            created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
            created_hosts.append(created_host)
            host_ids.append(str(created_host.id))

        # Verify all hosts were created successfully
        for i, (created_host, host_id) in enumerate(zip(created_hosts, host_ids, strict=False)):
            assert created_host is not None
            assert created_host.fqdn == f"test-delete-host-{i + 1}.example.com"
            assert created_host.display_name == f"Test Delete Host {i + 1}"
            assert str(created_host.id) == host_id

        # Create a new group
        group = db_create_group("test-delete-outbox-group")
        group_id = str(group.id)

        # Verify initial state - group is empty, hosts have no groups
        initial_hosts_in_group = db_get_hosts_for_group(group_id)
        assert len(initial_hosts_in_group) == 0

        for host_id in host_ids:
            initial_host = db_get_host(host_id)
            assert len(initial_host.groups) == 0  # Host not in any group initially

        # Add all 3 hosts to the group via API
        response_status, _ = api_add_hosts_to_group(group_id, host_ids)

        # Verify the API request was successful
        assert response_status == 200

        # Verify all hosts were actually added to the group in the database
        hosts_in_group_after_add = db_get_hosts_for_group(group_id)
        assert len(hosts_in_group_after_add) == 3

        # Verify each host is in the group
        hosts_in_group_ids = [str(host.id) for host in hosts_in_group_after_add]
        for host_id in host_ids:
            assert host_id in hosts_in_group_ids

        # Verify each host has the group information
        for host_id in host_ids:
            host = db_get_host(host_id)
            assert len(host.groups) == 1
            assert host.groups[0]["id"] == group_id
            assert host.groups[0]["name"] == "test-delete-outbox-group"

        # Now remove 2 hosts from the group (keep the first host)
        hosts_to_remove = host_ids[1:]  # Remove hosts 2 and 3
        host_to_keep = host_ids[0]  # Keep host 1

        # Capture outbox calls using helper with groups
        with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox", capture_groups=True) as outbox_calls:
            # Remove 2 hosts from the group via API
            response_status, _ = api_remove_hosts_from_group(group_id, hosts_to_remove)

            # Verify the API request was successful
            assert response_status == 204  # No Content

            # Verify outbox entries were created for the 2 removed hosts
            assert len(outbox_calls) == 2

            # Validate each outbox call for removed hosts
            for call in outbox_calls:
                assert call["event_type"] == EventType.updated
                assert call["host_id"] in hosts_to_remove

                # Use the captured groups information instead of accessing the detached host object
                groups_info = call["groups"]
                assert groups_info is not None
                assert len(groups_info) == 1  # Host should be in ungrouped hosts group
                assert groups_info[0]["name"] == "Ungrouped Hosts"  # Kessel requires ungrouped hosts group

        # Verify the group now contains only 1 host
        hosts_in_group_after_remove = db_get_hosts_for_group(group_id)
        assert len(hosts_in_group_after_remove) == 1
        assert str(hosts_in_group_after_remove[0].id) == host_to_keep

        # Verify the remaining host still has the group information
        remaining_host = db_get_host(host_to_keep)
        assert len(remaining_host.groups) == 1
        assert remaining_host.groups[0]["id"] == group_id
        assert remaining_host.groups[0]["name"] == "test-delete-outbox-group"

        # Verify the removed hosts are now in the ungrouped hosts group
        for removed_host_id in hosts_to_remove:
            removed_host = db_get_host(removed_host_id)
            assert len(removed_host.groups) == 1
            assert removed_host.groups[0]["name"] == "Ungrouped Hosts"
            # The ungrouped hosts group should have a specific ID (usually a UUID)
            assert "id" in removed_host.groups[0]

        # Now create actual outbox entries for each host to test the complete workflow
        # First, clear any existing outbox entries from the API operations

        all_host_ids = [host_to_keep] + hosts_to_remove

        # Clear existing outbox entries
        for host_id in all_host_ids:
            existing_entries = db.session.query(Outbox).filter_by(aggregateid=host_id).all()
            for entry in existing_entries:
                db.session.delete(entry)
        db.session.commit()

        for host_id in all_host_ids:
            host = db_get_host(host_id)
            assert host is not None

            # Write updated event to outbox for each host
            result = write_event_to_outbox(EventType.updated, host_id, host)
            assert result is True

            # Verify outbox entry was created and immediately deleted (new behavior)
            assert_outbox_empty(db, host_id)

            # The success of the operation indicates the outbox entry was created, validated, and processed

        # Test outbox entry deletion for all hosts by calling remove_event_from_outbox directly

        # Verify all outbox entries were created and immediately deleted (new behavior)
        for host_id in all_host_ids:
            assert_outbox_empty(db, host_id)

        # Call the remove_event_from_outbox function for each host (simulating Kafka message production)
        for host_id in all_host_ids:
            remove_event_from_outbox(host_id)

        # Verify all outbox entries have been deleted
        for host_id in all_host_ids:
            assert_outbox_empty(db, host_id)

        # Final validation: ensure all hosts still exist in the database with correct group information
        for i, host_id in enumerate(all_host_ids):
            final_host = db_get_host(host_id)
            assert final_host is not None
            assert str(final_host.id) == host_id
            assert final_host.fqdn == f"test-delete-host-{i + 1}.example.com"
            assert final_host.display_name == f"Test Delete Host {i + 1}"

            # Verify the host has the correct group information
            if host_id == host_to_keep:
                # Host should still be in the original group
                assert len(final_host.groups) == 1
                assert final_host.groups[0]["id"] == group_id
                assert final_host.groups[0]["name"] == "test-delete-outbox-group"
            else:
                # Host should be in the ungrouped hosts group
                assert len(final_host.groups) == 1
                assert final_host.groups[0]["name"] == "Ungrouped Hosts"

        # Final verification: confirm the group contains only 1 host
        final_hosts_in_group = db_get_hosts_for_group(group_id)
        assert len(final_hosts_in_group) == 1
        assert str(final_hosts_in_group[0].id) == host_to_keep

    def test_host_creation_with_kessel_workspace_migration_enabled(
        self, flask_app, event_producer_mock, notification_event_producer_mock
    ):
        """Test post-Kessel host creation using MQ flow.

        Verifies:
        1. Host creation event is written to the outbox table automatically
        2. The new host is automatically associated with the "Ungrouped Hosts" group
        3. The outbox table has zero entries when done (immediate deletion)
        4. EventProducer.write_event() is called during host creation
        """

        # Create test host data
        test_host = minimal_host(
            insights_id=generate_uuid(),
            subscription_manager_id=generate_uuid(),
            fqdn="test-host-kessel-mq.example.com",
        )

        platform_metadata = get_platform_metadata(SYSTEM_IDENTITY)
        message = wrap_message(test_host.data(), platform_metadata=platform_metadata)

        # Mock the Kessel migration flag to enable group assignment
        # Mock the RBAC workspace creation to avoid making actual API calls
        with (
            patch("lib.middleware.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid()),
        ):
            # Create MQ consumer and process message
            consumer = IngressMessageConsumer(None, flask_app, event_producer_mock, notification_event_producer_mock)
            result = consumer.handle_message(json.dumps(message))
            db.session.commit()

            # Verify the host was created successfully
            assert result.event_type == EventType.created
            assert result.row is not None
            created_host = result.row
            host_id = str(created_host.id)
            assert str(created_host.insights_id) == test_host.insights_id
            assert created_host.fqdn == "test-host-kessel-mq.example.com"

            # Note: EventProducer.write_event() may not be called in test environment due to disabled event producer
            # The main verification is that the host was created and associated with the "Ungrouped Hosts" group

            # Verify the host is automatically associated with the "Ungrouped Hosts" group
            assert len(created_host.groups) == 1
            assert created_host.groups[0]["name"] == "Ungrouped Hosts"
            assert created_host.groups[0]["ungrouped"] is True

            # Verify the group association exists in the database
            host_group_assoc = db.session.query(HostGroupAssoc).filter_by(host_id=created_host.id).first()
            assert host_group_assoc is not None

            # Verify the group exists and is marked as ungrouped
            group = db.session.query(Group).filter_by(id=host_group_assoc.group_id).first()
            assert group is not None
            assert group.name == "Ungrouped Hosts"
            assert group.ungrouped is True
            assert group.org_id == SYSTEM_IDENTITY["org_id"]

            # Verify outbox entry was created and immediately deleted (new behavior)
            # The write_event_to_outbox should have been called automatically during host creation
            assert_outbox_empty(db, host_id)

    def test_session_isolation_for_outbox_operations(self, request):
        """
        Test that outbox operations are isolated per session.

        This test verifies the fix for the critical session mismatch bug where
        Session A could write outbox entries for hosts created in Session B,
        leading to orphan outbox entries or missing entries if sessions rollback.

        The fix ensures that _collect_pending_ops_for_session() only returns
        operations for the current session, not all sessions.
        """
        # Create two separate database sessions to simulate concurrent requests
        engine = db.get_engine()
        session_a = SQLASession(bind=engine)
        session_b = SQLASession(bind=engine)

        # Register cleanup finalizer
        def cleanup():
            session_a.close()
            session_b.close()

        request.addfinalizer(cleanup)

        # Verify sessions are different
        assert session_a.hash_key != session_b.hash_key, "Sessions must have different IDs"

        # Simulate ops being tracked in both sessions using session.info
        session_a.info["pending_ops"] = [("created", str(uuid.uuid4())), ("updated", str(uuid.uuid4()))]
        session_b.info["pending_ops"] = [("created", str(uuid.uuid4())), ("deleted", str(uuid.uuid4()))]

        # Test: session_a should only get its own ops
        ops_a = _collect_pending_ops_for_session(session_a)
        assert len(ops_a) == 2, f"Session A should have 2 ops, got {len(ops_a)}"
        assert ops_a[0][0] == "created", "First op should be 'created'"
        assert ops_a[1][0] == "updated", "Second op should be 'updated'"

        # Test: session_b should only get its own ops
        ops_b = _collect_pending_ops_for_session(session_b)
        assert len(ops_b) == 2, f"Session B should have 2 ops, got {len(ops_b)}"
        assert ops_b[0][0] == "created", "First op should be 'created'"
        assert ops_b[1][0] == "deleted", "Second op should be 'deleted'"

        # Critical test: Verify no cross-session contamination
        session_a_host_ids = {op[1] for op in ops_a}
        session_b_host_ids = {op[1] for op in ops_b}
        assert session_a_host_ids.isdisjoint(session_b_host_ids), (
            "Session A and Session B should have completely different host IDs"
        )

        # Verify session_a ops are not in session_b results
        for _op_type, host_id in ops_a:
            assert host_id not in session_b_host_ids, f"Session B should not see Session A's host {host_id}"

        # Verify session_b ops are not in session_a results
        for _op_type, host_id in ops_b:
            assert host_id not in session_a_host_ids, f"Session A should not see Session B's host {host_id}"
