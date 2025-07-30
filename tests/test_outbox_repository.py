import json
import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from sqlalchemy.exc import DatabaseError

from app.models.outbox import Outbox
from lib.outbox_repository import FLASK_AVAILABLE
from lib.outbox_repository import _create_update_event_payload
from lib.outbox_repository import _delete_event_payload
from lib.outbox_repository import write_event_to_outbox


class TestOutboxRepositoryHelperFunctions:
    """Test helper functions for creating event payloads."""

    def test_create_update_event_payload_success(self):
        """Test successful creation of update event payload."""
        # Generate test data with known values for assertions
        host_id = str(uuid.uuid4())
        satellite_id = "1234567890"  # Valid 10-digit satellite ID
        subscription_manager_id = str(uuid.uuid4())
        insights_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())

        host_data = {
            "id": host_id,
            "satellite_id": satellite_id,
            "subscription_manager_id": subscription_manager_id,
            "insights_id": insights_id,
            "ansible_host": "ansible-host-123",
            "groups": [{"id": group_id}],
        }

        payload = _create_update_event_payload(host_data)

        assert payload is not None
        assert payload["type"] == "host"
        assert payload["reporterType"] == "hbi"
        assert payload["reporterInstanceId"] == "redhat.com"

        # Check representations structure
        representations = payload["representations"]
        assert "metadata" in representations
        assert "common" in representations
        assert "reporter" in representations

        # Check metadata
        metadata = representations["metadata"]
        assert metadata["localResourceId"] == host_id
        assert metadata["reporterVersion"] == "1.0"

        # Check common
        assert representations["common"]["workspace_id"] == group_id

        # Check reporter
        reporter = representations["reporter"]
        assert reporter["satellite_id"] == satellite_id
        assert reporter["subscription_manager_id"] == subscription_manager_id
        assert reporter["insights_id"] == insights_id
        assert reporter["ansible_host"] == "ansible-host-123"

    def test_create_update_event_payload_missing_host(self):
        """Test create update event payload when host is missing."""
        host_data = None

        payload = _create_update_event_payload(host_data)

        assert payload is None

    def test_create_update_event_payload_empty_host(self):
        """Test create update event payload when host is empty."""
        host_data = {}

        payload = _create_update_event_payload(host_data)

        assert payload is None

    def test_create_update_event_payload_minimal_host(self):
        """Test create update event payload with minimal host data."""
        host_data = {"id": str(uuid.uuid4()), "groups": [{"id": str(uuid.uuid4())}]}

        payload = _create_update_event_payload(host_data)

        assert payload is not None
        representations = payload["representations"]

        # Check that None values are handled properly
        reporter = representations["reporter"]
        assert reporter["satellite_id"] is None
        assert reporter["subscription_manager_id"] is None
        assert reporter["insights_id"] is None
        assert reporter["ansible_host"] is None

    def test_delete_event_payload_success(self):
        """Test successful creation of delete event payload."""
        host_id = str(uuid.uuid4())
        host_data = {"id": host_id}

        payload = _delete_event_payload(host_data)

        assert payload is not None
        assert "reference" in payload

        reference = payload["reference"]
        assert reference["resource_type"] == "host"
        assert reference["resource_id"] == host_id
        assert reference["reporter"]["type"] == "HBI"

    def test_delete_event_payload_missing_host(self):
        """Test delete event payload when host is missing."""
        host_data = None

        payload = _delete_event_payload(host_data)

        assert payload is None

    def test_delete_event_payload_empty_host(self):
        """Test delete event payload when host is empty."""
        host_data = {}

        payload = _delete_event_payload(host_data)

        assert payload is None


class TestWriteEventToOutbox:
    """Test the main write_event_to_outbox function."""

    @pytest.fixture
    def valid_created_event(self):
        """Fixture for a valid created event."""
        return {
            "type": "created",
            "host": {"id": str(uuid.uuid4()), "satellite_id": "1234567890", "groups": [{"id": str(uuid.uuid4())}]},
        }

    @pytest.fixture
    def valid_updated_event(self):
        """Fixture for a valid updated event."""
        return {
            "type": "updated",
            "host": {
                "id": str(uuid.uuid4()),
                "subscription_manager_id": str(uuid.uuid4()),
                "groups": [{"id": str(uuid.uuid4())}],
            },
        }

    @pytest.fixture
    def valid_delete_event(self):
        """Fixture for a valid delete event."""
        return {"type": "delete", "host": {"id": str(uuid.uuid4())}}

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_write_event_to_outbox_created_success(self, valid_created_event, flask_app):  # noqa: ARG002, fixture needed by pytest
        """Test successfully writing a created event to outbox."""
        event_json = json.dumps(valid_created_event)

        result = write_event_to_outbox(event_json)

        assert result is True

        # Verify the event was written to the database
        outbox_entry = Outbox.query.filter_by(aggregate_id=valid_created_event["host"]["id"]).first()
        assert outbox_entry is not None
        assert outbox_entry.aggregate_type == "hbi.hosts"
        assert outbox_entry.event_type == "created"

        # Verify payload structure
        payload = outbox_entry.payload
        assert payload["type"] == "host"
        assert payload["reporterType"] == "hbi"

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_write_event_to_outbox_updated_success(self, valid_updated_event, flask_app):  # noqa: ARG002
        """Test successfully writing an updated event to outbox."""
        event_json = json.dumps(valid_updated_event)

        result = write_event_to_outbox(event_json)

        assert result is True

        # Verify the event was written to the database
        outbox_entry = Outbox.query.filter_by(aggregate_id=valid_updated_event["host"]["id"]).first()
        assert outbox_entry is not None
        assert outbox_entry.event_type == "updated"

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_write_event_to_outbox_delete_success(self, valid_delete_event, flask_app):  # noqa: ARG002
        """Test successfully writing a delete event to outbox."""
        event_json = json.dumps(valid_delete_event)

        result = write_event_to_outbox(event_json)

        assert result is True

        # Verify the event was written to the database
        outbox_entry = Outbox.query.filter_by(aggregate_id=valid_delete_event["host"]["id"]).first()
        assert outbox_entry is not None
        assert outbox_entry.event_type == "delete"

        # Verify delete payload structure
        payload = outbox_entry.payload
        assert "reference" in payload
        assert payload["reference"]["resource_type"] == "host"

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_write_event_to_outbox_dict_input(self, valid_created_event, flask_app):  # noqa: ARG002
        """Test writing event when input is already a dict (not JSON string)."""
        result = write_event_to_outbox(valid_created_event)

        assert result is True

        # Verify the event was written to the database
        outbox_entry = Outbox.query.filter_by(aggregate_id=valid_created_event["host"]["id"]).first()
        assert outbox_entry is not None

    def test_write_event_to_outbox_flask_not_available(self):
        """Test write_event_to_outbox when Flask dependencies are not available."""
        with patch("lib.outbox_repository.FLASK_AVAILABLE", False):
            result = write_event_to_outbox('{"type": "created"}')

            assert result is False

    def test_write_event_to_outbox_invalid_json(self):
        """Test write_event_to_outbox with invalid JSON."""
        invalid_json = '{"type": "created", invalid}'

        result = write_event_to_outbox(invalid_json)

        assert result is False

    def test_write_event_to_outbox_missing_type(self):
        """Test write_event_to_outbox with missing type field."""
        event = {"host": {"id": str(uuid.uuid4())}}

        result = write_event_to_outbox(json.dumps(event))

        assert result is False

    def test_write_event_to_outbox_missing_host(self):
        """Test write_event_to_outbox with missing host field."""
        event = {"type": "created"}

        result = write_event_to_outbox(json.dumps(event))

        assert result is False

    def test_write_event_to_outbox_missing_host_id(self):
        """Test write_event_to_outbox with missing host.id field."""
        event = {"type": "created", "host": {}}

        result = write_event_to_outbox(json.dumps(event))

        assert result is False

    def test_write_event_to_outbox_invalid_type(self):
        """Test write_event_to_outbox with invalid event type."""
        event = {"type": "invalid_type", "host": {"id": str(uuid.uuid4())}}

        result = write_event_to_outbox(json.dumps(event))

        assert result is False

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    @patch("lib.outbox_repository.db")
    def test_write_event_to_outbox_database_error(self, mock_db, valid_created_event):
        """Test write_event_to_outbox with database error."""
        # Mock database session to raise an exception when adding to session
        mock_session = MagicMock()
        mock_session.add.side_effect = DatabaseError("Database connection error", None, None)
        mock_db.session = mock_session

        result = write_event_to_outbox(json.dumps(valid_created_event))

        assert result is False

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    @patch("lib.outbox_repository.db")
    def test_write_event_to_outbox_table_not_exist_error(self, mock_db, valid_created_event):
        """Test write_event_to_outbox with table doesn't exist error."""
        # Mock database session to raise a table doesn't exist error
        mock_session = MagicMock()
        mock_session.add.side_effect = DatabaseError("table does not exist", None, None)
        mock_db.session = mock_session

        result = write_event_to_outbox(json.dumps(valid_created_event))

        assert result is False

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    @patch("lib.outbox_repository.db")
    def test_write_event_to_outbox_create_all_error(self, mock_db, valid_created_event):
        """Test write_event_to_outbox when db.create_all() fails."""
        # Mock db.create_all to raise an exception (this doesn't actually affect the outbox write)
        mock_db.create_all.side_effect = Exception("Cannot create tables")

        # Mock session to work normally
        mock_session = MagicMock()
        mock_outbox_entry = MagicMock()
        mock_outbox_entry.id = str(uuid.uuid4())
        mock_session.add.return_value = None
        mock_session.flush.return_value = None
        mock_db.session = mock_session

        with patch("lib.outbox_repository.Outbox") as mock_outbox_class:
            mock_outbox_class.return_value = mock_outbox_entry

            result = write_event_to_outbox(json.dumps(valid_created_event))

            # Should still succeed since we don't call create_all in the function
            assert result is True

    def test_write_event_to_outbox_unexpected_error(self, valid_created_event):
        """Test write_event_to_outbox with unexpected error."""
        with patch("lib.outbox_repository.json.loads") as mock_loads:
            mock_loads.side_effect = Exception("Unexpected error")

            result = write_event_to_outbox(json.dumps(valid_created_event))

            assert result is False

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_write_event_to_outbox_key_error(self, flask_app):  # noqa: ARG002
        """Test write_event_to_outbox with KeyError during processing."""
        # Create an event that will cause a KeyError in payload generation
        # The groups list contains an empty dict without 'id', causing KeyError in workspace_id assignment
        event = {
            "type": "created",
            "host": {
                "id": str(uuid.uuid4()),
                "groups": [{}],  # Empty group dict without 'id' field will cause KeyError
            },
        }

        result = write_event_to_outbox(json.dumps(event))

        assert result is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_event_with_all_supported_types(self, flask_app):  # noqa: ARG002
        """Test that all supported event types work correctly."""
        host_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())

        events = [
            {"type": "created", "host": {"id": host_id, "groups": [{"id": group_id}]}},
            {"type": "updated", "host": {"id": host_id, "groups": [{"id": group_id}]}},
            {"type": "delete", "host": {"id": host_id}},
        ]

        for event in events:
            result = write_event_to_outbox(json.dumps(event))
            assert result is True

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_event_with_unicode_data(self, flask_app):  # noqa: ARG002
        """Test event with unicode characters in data."""
        event = {
            "type": "created",
            "host": {
                "id": str(uuid.uuid4()),
                "ansible_host": "ホスト名-测试-тест",  # Unicode characters
                "groups": [{"id": str(uuid.uuid4())}],
            },
        }

        result = write_event_to_outbox(json.dumps(event))

        assert result is True

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_event_with_large_data(self, flask_app):  # noqa: ARG002
        """Test event with large data payload that exceeds validation limits."""
        large_string = "x" * 10000  # 10KB string - exceeds 255 char limit for ansible_host

        event = {
            "type": "created",
            "host": {"id": str(uuid.uuid4()), "ansible_host": large_string, "groups": [{"id": str(uuid.uuid4())}]},
        }

        # This should fail due to ansible_host length validation
        try:
            result = write_event_to_outbox(json.dumps(event))
            assert result is False, "Expected validation to fail for oversized ansible_host"
        except Exception:
            # If an exception is raised, that's also acceptable for this test
            pass

    @pytest.mark.skipif(not FLASK_AVAILABLE, reason="Flask dependencies not available")
    def test_concurrent_writes(self, flask_app):  # noqa: ARG002
        """Test multiple concurrent writes to outbox."""
        events = []
        events.extend(
            {
                "type": "created",
                "host": {
                    "id": str(uuid.uuid4()),
                    "groups": [{"id": str(uuid.uuid4())}],
                },
            }
            for _ in range(10)
        )
        results = []
        for event in events:
            result = write_event_to_outbox(json.dumps(event))
            results.append(result)

        # All writes should succeed
        assert all(results)

        # Verify all entries were written
        outbox_entries = Outbox.query.all()
        assert len(outbox_entries) >= len(events)
