from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
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
from app.queue.enums import ConsumerApplication
from tests.helpers.test_utils import generate_uuid

# Application test data configuration: (app_name, model_class, sample_data, fields_to_verify)
APPLICATION_TEST_DATA = [
    pytest.param(
        ConsumerApplication.ADVISOR,
        HostAppDataAdvisor,
        {"recommendations": 5, "incidents": 2},
        {"recommendations": 5, "incidents": 2},
        id="advisor",
    ),
    pytest.param(
        ConsumerApplication.VULNERABILITY,
        HostAppDataVulnerability,
        {
            "total_cves": 50,
            "critical_cves": 5,
            "high_severity_cves": 10,
            "cves_with_security_rules": 8,
            "cves_with_known_exploits": 3,
        },
        {"total_cves": 50, "critical_cves": 5, "high_severity_cves": 10},
        id="vulnerability",
    ),
    pytest.param(
        ConsumerApplication.PATCH,
        HostAppDataPatch,
        {
            "advisories_rhsa_applicable": 10,
            "advisories_rhba_applicable": 5,
            "advisories_rhsa_installable": 8,
            "packages_installable": 50,
            "template_name": "baseline-template",
        },
        {
            "advisories_rhsa_applicable": 10,
            "advisories_rhba_applicable": 5,
            "advisories_rhsa_installable": 8,
            "packages_installable": 50,
            "template_name": "baseline-template",
        },
        id="patch",
    ),
    pytest.param(
        ConsumerApplication.REMEDIATIONS,
        HostAppDataRemediations,
        {"remediations_plans": 7},
        {"remediations_plans": 7},
        id="remediations",
    ),
    pytest.param(
        ConsumerApplication.COMPLIANCE,
        HostAppDataCompliance,
        {
            "policies": [{"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "name": "Policy 1"}],
            "last_scan": datetime.now(UTC).isoformat(),
        },
        {"policies": [{"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "name": "Policy 1"}]},
        id="compliance",
    ),
    pytest.param(
        ConsumerApplication.MALWARE,
        HostAppDataMalware,
        {"last_status": "clean", "last_matches": 0, "last_scan": datetime.now(UTC).isoformat(), "total_matches": 0},
        {"last_status": "clean", "last_matches": 0, "total_matches": 0},
        id="malware",
    ),
    pytest.param(
        ConsumerApplication.IMAGE_BUILDER,
        HostAppDataImageBuilder,
        {"image_name": "rhel-9-base", "image_status": "active"},
        {"image_name": "rhel-9-base", "image_status": "active"},
        id="image_builder",
    ),
]


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
        with pytest.raises(ValidationException, match="is not a valid ConsumerApplication"):
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


class TestHostAppMessageConsumerAllApplications:
    """Test HostAppMessageConsumer with all application types using parametrized tests."""

    @pytest.mark.parametrize("app_name,model_class,sample_data,fields_to_verify", APPLICATION_TEST_DATA)
    def test_upsert_new_record(
        self, host_app_consumer, db_create_host, app_name, model_class, sample_data, fields_to_verify
    ):
        """Test inserting new data for all application types."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        message = create_host_app_message(org_id=org_id, host_id=host_id, data=sample_data)

        headers = [("application", app_name.encode("utf-8")), ("request_id", generate_uuid().encode("utf-8"))]
        result = host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(model_class).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        # Verify all specified fields
        for field_name, expected_value in fields_to_verify.items():
            assert getattr(app_data, field_name) == expected_value
        # Advisor has last_updated field
        if hasattr(app_data, "last_updated"):
            assert app_data.last_updated is not None
        assert result is not None

    @pytest.mark.parametrize("app_name,model_class,sample_data,fields_to_verify", APPLICATION_TEST_DATA)
    def test_upsert_update_record(
        self, host_app_consumer, db_create_host, app_name, model_class, sample_data, fields_to_verify
    ):
        """Test updating existing data for all application types."""
        host = db_create_host()
        org_id = host.org_id
        host_id = str(host.id)

        # Insert initial data
        message1 = create_host_app_message(org_id=org_id, host_id=host_id, data=sample_data)
        headers = [("application", app_name.encode("utf-8")), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message1), headers=headers)

        # Create updated data by modifying numeric fields or using different values
        updated_data = sample_data.copy()
        for key, value in updated_data.items():
            if isinstance(value, int):
                updated_data[key] = value + 5
            elif isinstance(value, str) and key not in ["last_scan", "last_status"]:
                updated_data[key] = f"updated_{value}"

        # Update with new data
        message2 = create_host_app_message(org_id=org_id, host_id=host_id, data=updated_data)
        headers2 = [("application", app_name.encode("utf-8")), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message2), headers=headers2)

        # Verify the record was updated
        app_data = db.session.query(model_class).filter_by(org_id=org_id, host_id=host.id).first()

        assert app_data is not None
        # Verify at least one field was updated
        for field_name in fields_to_verify.keys():
            actual_value = getattr(app_data, field_name)
            original_value = sample_data[field_name]
            if isinstance(original_value, int):
                assert actual_value == original_value + 5
            elif isinstance(original_value, str) and field_name not in ["last_scan", "last_status"]:
                assert actual_value == f"updated_{original_value}"

    @pytest.mark.parametrize("app_name,model_class,sample_data,fields_to_verify", APPLICATION_TEST_DATA)
    def test_batch_processing(
        self, host_app_consumer, db_create_host, app_name, model_class, sample_data, fields_to_verify
    ):
        """Test processing multiple hosts in a single message for all application types."""
        host1 = db_create_host()
        host2 = db_create_host(extra_data={"org_id": host1.org_id})
        org_id = host1.org_id

        # Create data for second host (slightly different values)
        data2 = sample_data.copy()
        for key, value in data2.items():
            if isinstance(value, int):
                data2[key] = max(1, value - 2)  # Different value, but keep positive

        message = {
            "org_id": org_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "hosts": [
                {"id": str(host1.id), "data": sample_data},
                {"id": str(host2.id), "data": data2},
            ],
        }

        headers = [("application", app_name.encode("utf-8")), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        # Verify both records were created
        app_data1 = db.session.query(model_class).filter_by(org_id=org_id, host_id=host1.id).first()
        app_data2 = db.session.query(model_class).filter_by(org_id=org_id, host_id=host2.id).first()

        assert app_data1 is not None
        assert app_data2 is not None
        # Verify first host has original data
        first_field = list(fields_to_verify.keys())[0]
        assert getattr(app_data1, first_field) == sample_data[first_field]
        # Verify second host has different data (for numeric fields)
        if isinstance(sample_data[first_field], int):
            assert getattr(app_data2, first_field) == data2[first_field]


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

        # template_name should be max 255 chars
        patch_data = {"advisories_rhsa_installable": 10, "template_name": "x" * 300}
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

        compliance_data = {
            "policies": [{"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "name": "Policy 1"}],
            "last_scan": "2025-01-10T12:00:00Z",
        }
        message = create_host_app_message(org_id=org_id, host_id=host_id, data=compliance_data)

        headers = [("application", b"compliance"), ("request_id", generate_uuid().encode("utf-8"))]
        host_app_consumer.handle_message(json.dumps(message), headers=headers)

        app_data = db.session.query(HostAppDataCompliance).filter_by(org_id=org_id, host_id=host.id).first()
        assert app_data is not None
        assert app_data.policies[0]["id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert app_data.policies[0]["name"] == "Policy 1"
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
