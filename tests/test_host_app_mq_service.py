from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from marshmallow import ValidationError

from app.exceptions import ValidationException
from app.models import db
from app.models.host_app_data import HostAppDataAdvisor
from app.models.host_app_data import HostAppDataCompliance
from app.models.host_app_data import HostAppDataImageBuilder
from app.models.host_app_data import HostAppDataMalware
from app.models.host_app_data import HostAppDataPatch
from app.models.host_app_data import HostAppDataRemediations
from app.models.host_app_data import HostAppDataVulnerability
from app.queue.host_mq import HostAppMessageConsumer
from tests.helpers.test_utils import generate_uuid


@pytest.fixture
def host_app_consumer(flask_app, event_producer):
    """Fixture to create HostAppMessageConsumer for testing."""
    fake_consumer = MagicMock()
    fake_notification_event_producer = MagicMock()
    return HostAppMessageConsumer(fake_consumer, flask_app, event_producer, fake_notification_event_producer)


def create_host_app_message(
    org_id: str,
    host_id: str,
    data: dict,
    timestamp: str | None = None,  # noqa: ARG001
):
    """Helper function to create a valid host app data message.

    This helper returns only the message body - tests must pass application/request_id as context kwargs.
    """
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()

    return {
        "org_id": org_id,
        "timestamp": timestamp,
        "hosts": [{"id": host_id, "data": data}],
    }


class TestHostAppMessageConsumerValidation:
    """Test validation logic for HostAppMessageConsumer."""

    def test_missing_application_field(self, host_app_consumer):
        """Test that missing application header raises ValidationException."""
        message = {
            "org_id": "test-org-id",
            "timestamp": datetime.now(UTC).isoformat(),
            "hosts": [],
        }

        # Pass empty headers - simulates missing Kafka header
        with pytest.raises(ValidationException, match="Missing 'application'"):
            host_app_consumer.handle_message(json.dumps(message), headers=[])

    def test_unknown_application(self, host_app_consumer):
        """Test that unknown application raises ValidationException."""
        message = create_host_app_message(org_id="test-org-id", host_id=generate_uuid(), data={})

        headers = [
            ("application", b"unknown_app"),
            ("request_id", generate_uuid().encode("utf-8")),
        ]
        with pytest.raises(ValidationException, match="Unknown application"):
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

    def test_invalid_message_format(self, host_app_consumer):
        """Test that invalid JSON raises exception."""
        headers = [("application", b"advisor"), ("request_id", b"test-123")]
        with pytest.raises(Exception):  # noqa: B017
            host_app_consumer.handle_message("invalid json", headers=headers)

    def test_missing_required_fields(self, host_app_consumer):
        """Test that missing required fields raises ValidationError."""
        message = {
            # Missing org_id, timestamp, and hosts
        }

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        with pytest.raises(ValidationError):
            host_app_consumer.handle_message(json.dumps(message), headers=headers)


class TestHostAppMessageConsumerAdvisor:
    """Test HostAppMessageConsumer with Advisor data."""

    def test_advisor_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new Advisor data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        advisor_data = {"recommendations": 5, "incidents": 2}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=advisor_data)

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        result = host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.recommendations == 5
        assert app_data.incidents == 2
        assert app_data.last_updated is not None
        assert result is not None

    def test_advisor_upsert_update_record(self, host_app_consumer, db_create_host):
        """Test updating existing Advisor data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        # Insert initial data
        initial_data = {"recommendations": 5, "incidents": 2}
        message1 = create_host_app_message(org_id=org_id, host_id=host_id, data=initial_data)
        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message1), headers=headers)

        # Update with new data
        updated_data = {"recommendations": 10, "incidents": 3}
        message2 = create_host_app_message(org_id=org_id, host_id=host_id, data=updated_data)
        headers2 = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message2), headers=headers2)

        # Verify the record was updated
        app_data = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.recommendations == 10
        assert app_data.incidents == 3

    def test_advisor_batch_processing(self, host_app_consumer, db_create_host):
        """Test processing multiple hosts in a single message."""
        host1 = db_create_host()
        host2 = db_create_host(extra_data={"org_id": host1.org_id})
        org_id = host1.org_id

        message = {
            "org_id": org_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "hosts": [
                {"id": str(host1.id), "data": {"recommendations": 5, "incidents": 2}},
                {"id": str(host2.id), "data": {"recommendations": 3, "incidents": 1}},
            ],
        }

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        # Verify both records were created
        app_data1 = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host1.id).first()
        app_data2 = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host2.id).first()

        assert app_data1 is not None
        assert app_data1.recommendations == 5
        assert app_data2 is not None
        assert app_data2.recommendations == 3


class TestHostAppMessageConsumerVulnerability:
    """Test HostAppMessageConsumer with Vulnerability data."""

    def test_vulnerability_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new Vulnerability data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        vuln_data = {
            "total_cves": 50,
            "critical_cves": 5,
            "high_severity_cves": 10,
            "cves_with_security_rules": 8,
            "cves_with_known_exploits": 3,
        }
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=vuln_data)

        headers = [("application", b"vulnerability"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataVulnerability).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.total_cves == 50
        assert app_data.critical_cves == 5
        assert app_data.high_severity_cves == 10


class TestHostAppMessageConsumerPatch:
    """Test HostAppMessageConsumer with Patch data."""

    def test_patch_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new Patch data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        patch_data = {"installable_advisories": 15, "template": "baseline-template", "rhsm_locked_version": "9.4"}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=patch_data)

        headers = [("application", b"patch"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataPatch).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.installable_advisories == 15
        assert app_data.template == "baseline-template"
        assert app_data.rhsm_locked_version == "9.4"


class TestHostAppMessageConsumerRemediations:
    """Test HostAppMessageConsumer with Remediations data."""

    def test_remediations_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new Remediations data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        remediation_data = {"remediations_plans": 7}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=remediation_data)

        headers = [("application", b"remediations"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataRemediations).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.remediations_plans == 7


class TestHostAppMessageConsumerCompliance:
    """Test HostAppMessageConsumer with Compliance data."""

    def test_compliance_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new Compliance data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        compliance_data = {"policies": 3, "last_scan": datetime.now(UTC).isoformat()}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=compliance_data)

        headers = [("application", b"compliance"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataCompliance).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.policies == 3
        assert app_data.last_scan is not None


class TestHostAppMessageConsumerMalware:
    """Test HostAppMessageConsumer with Malware data."""

    def test_malware_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new Malware data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        malware_data = {
            "last_status": "clean",
            "last_matches": 0,
            "last_scan": datetime.now(UTC).isoformat(),
        }
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=malware_data)

        headers = [("application", b"malware"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataMalware).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.last_status == "clean"
        assert app_data.last_matches == 0
        assert app_data.last_scan is not None


class TestHostAppMessageConsumerImageBuilder:
    """Test HostAppMessageConsumer with ImageBuilder data."""

    def test_image_builder_upsert_new_record(self, host_app_consumer, db_create_host):
        """Test inserting new ImageBuilder data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        image_builder_data = {"image_name": "rhel-9-base", "image_status": "active"}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=image_builder_data)

        headers = [("application", b"image_builder"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataImageBuilder).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.image_name == "rhel-9-base"
        assert app_data.image_status == "active"


class TestHostAppMessageConsumerMetrics:
    """Test that metrics are properly recorded."""

    @patch("app.queue.host_mq.metrics")
    def test_metrics_on_success(self, mock_metrics, host_app_consumer, db_create_host):
        """Test that success metrics are incremented."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        advisor_data = {"recommendations": 5, "incidents": 2}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=advisor_data)

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        mock_metrics.host_app_data_processing_success.labels.assert_called_with(application="advisor", org_id=org_id)

    @patch("app.queue.host_mq.metrics")
    def test_metrics_on_parsing_failure(self, mock_metrics, host_app_consumer):
        """Test that parsing failure metrics are incremented on invalid JSON."""
        headers = [("application", b"advisor"), ("request_id", b"test-123")]
        with pytest.raises(Exception):  # noqa: B017
            host_app_consumer.handle_message("invalid json {{{", headers=headers)

        mock_metrics.host_app_data_parsing_failure.labels.assert_called_with(application="advisor")

    @patch("app.queue.host_mq.metrics")
    def test_metrics_on_validation_failure(self, mock_metrics, host_app_consumer):
        """Test that validation failure metrics are incremented on validation errors."""
        message = {}  # Missing required fields

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        with pytest.raises(ValidationError):
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

        mock_metrics.host_app_data_validation_failure.labels.assert_called_with(
            application="advisor", reason="schema_validation_error"
        )

    @patch("app.queue.host_mq.metrics")
    def test_metrics_on_unknown_application(self, mock_metrics, host_app_consumer):
        """Test that validation failure metrics are incremented for unknown application."""
        message = create_host_app_message(org_id="test-org-id", host_id=generate_uuid(), data={})

        headers = [("application", b"unknown_app"), ("request_id", generate_uuid().encode("utf-8"))]
        with pytest.raises(ValidationException):
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

        mock_metrics.host_app_data_validation_failure.labels.assert_called_with(
            application="unknown_app", reason="unknown_application"
        )

    @patch("app.queue.host_mq.metrics")
    def test_metrics_on_missing_application(self, mock_metrics, host_app_consumer):
        """Test that validation failure metrics are incremented for missing application header."""
        message = {
            "org_id": "test-org-id",
            "timestamp": datetime.now(UTC).isoformat(),
            "hosts": [],
        }

        # Pass empty headers - simulates missing Kafka header
        with pytest.raises(ValidationException):
            host_app_consumer.handle_message(json.dumps(message), headers=[])

        mock_metrics.host_app_data_validation_failure.labels.assert_called_with(
            application="unknown", reason="missing_application_header"
        )


class TestHostAppMessageConsumerEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_hosts_list(self, host_app_consumer):
        """Test handling of message with empty hosts list."""
        message = {
            "org_id": "test-org-id",
            "timestamp": datetime.now(UTC).isoformat(),
            "hosts": [],
        }

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        result = host_app_consumer.handle_message(json.dumps(message), headers=headers)

        assert result is not None

    @patch("app.queue.host_mq.db.session.execute")
    @patch("app.queue.host_mq.metrics")
    def test_database_error_handling(self, mock_metrics, mock_execute, host_app_consumer, db_create_host):
        """Test that database errors are properly handled and metrics are recorded."""
        from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

        mock_execute.side_effect = SQLAlchemyOperationalError("Database connection failed", None, None)

        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        advisor_data = {"recommendations": 5, "incidents": 2}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=advisor_data)

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        with pytest.raises(SQLAlchemyOperationalError, match="Database connection failed"):
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

        mock_metrics.host_app_data_processing_failure.labels.assert_called_with(
            application="advisor", reason="db_operational_error"
        )

    def test_null_values_in_data(self, host_app_consumer, db_create_host):
        """Test handling of null values in application data."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        # Advisor data with null values
        advisor_data = {"recommendations": None, "incidents": None}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=advisor_data)

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        assert app_data.recommendations is None
        assert app_data.incidents is None


class TestHostAppDataValidation:
    """Test application-specific data validation according to host_app_events.spec.yaml."""

    def test_advisor_data_valid(self, host_app_consumer, db_create_host):
        """Test that valid Advisor data is accepted."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        advisor_data = {"recommendations": 5, "incidents": 2}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=advisor_data)

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host.id).first()
        assert app_data is not None
        assert app_data.recommendations == 5
        assert app_data.incidents == 2

    def test_advisor_data_invalid_type(self, host_app_consumer, db_create_host):
        """Test that Advisor data with wrong types is rejected."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        # recommendations should be int, not string
        advisor_data = {"recommendations": "not_a_number", "incidents": 2}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=advisor_data)

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        with patch("app.queue.host_mq.metrics.host_app_data_validation_failure") as mock_metric:
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

            # Should have incremented validation failure metric
            mock_metric.labels.assert_called_with(application="advisor", reason="invalid_host_data")
            mock_metric.labels.return_value.inc.assert_called_once()

        # Should not have been inserted into database
        app_data = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host.id).first()
        assert app_data is None

    def test_vulnerability_data_valid(self, host_app_consumer, db_create_host):
        """Test that valid Vulnerability data is accepted."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        vuln_data = {
            "total_cves": 50,
            "critical_cves": 5,
            "high_severity_cves": 10,
            "cves_with_security_rules": 8,
            "cves_with_known_exploits": 3,
        }
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=vuln_data)

        headers = [("application", b"vulnerability"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataVulnerability).filter_by(org_id=org_id, host_id=host.id).first()
        assert app_data is not None
        assert app_data.total_cves == 50
        assert app_data.critical_cves == 5

    def test_patch_data_maxlength_validation(self, host_app_consumer, db_create_host):
        """Test that Patch data exceeding maxLength is rejected."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        # template should be max 255 chars
        patch_data = {"installable_advisories": 10, "template": "x" * 300, "rhsm_locked_version": "8.5"}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=patch_data)

        headers = [("application", b"patch"), ("request_id", generate_uuid().encode("utf-8"))]
        with patch("app.queue.host_mq.metrics.host_app_data_validation_failure") as mock_metric:
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

            mock_metric.labels.assert_called_with(application="patch", reason="invalid_host_data")
            mock_metric.labels.return_value.inc.assert_called_once()

        app_data = db.session.query(HostAppDataPatch).filter_by(org_id=org_id, host_id=host.id).first()
        assert app_data is None

    def test_compliance_data_datetime_valid(self, host_app_consumer, db_create_host):
        """Test that Compliance data with valid datetime is accepted."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        compliance_data = {"policies": 3, "last_scan": "2025-01-10T12:00:00Z"}
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=compliance_data)

        headers = [("application", b"compliance"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataCompliance).filter_by(org_id=org_id, host_id=host.id).first()
        assert app_data is not None
        assert app_data.policies == 3
        assert app_data.last_scan is not None

    def test_multiple_hosts_partial_validation_failure(self, host_app_consumer, db_create_host):
        """Test that when one host has invalid data, others are still processed."""
        host1 = db_create_host()
        org_id = host1.org_id
        host2 = db_create_host(extra_data={"org_id": org_id})
        host3 = db_create_host(extra_data={"org_id": org_id})

        # Create message with 3 hosts: 1 invalid, 2 valid
        message = {
            "org_id": org_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "hosts": [
                {"id": str(host1.id), "data": {"recommendations": 5, "incidents": 2}},  # Valid
                {"id": str(host2.id), "data": {"recommendations": "invalid", "incidents": 1}},  # Invalid
                {"id": str(host3.id), "data": {"recommendations": 10, "incidents": 3}},  # Valid
            ],
        }

        headers = [("application", b"advisor"), ("request_id", generate_uuid().encode("utf-8"))]
        with patch("app.queue.host_mq.metrics.host_app_data_validation_failure") as mock_metric:
            host_app_consumer.handle_message(json.dumps(message), headers=headers)

            # Should have incremented validation failure metric once (for host2)
            mock_metric.labels.assert_called_with(application="advisor", reason="invalid_host_data")
            mock_metric.labels.return_value.inc.assert_called_once()

        # host1 and host3 should be in database
        app_data1 = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host1.id).first()
        assert app_data1 is not None
        assert app_data1.recommendations == 5

        # host2 should not be in database
        app_data2 = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host2.id).first()
        assert app_data2 is None

        # host3 should be in database
        app_data3 = db.session.query(HostAppDataAdvisor).filter_by(org_id=org_id, host_id=host3.id).first()
        assert app_data3 is not None
        assert app_data3.recommendations == 10
