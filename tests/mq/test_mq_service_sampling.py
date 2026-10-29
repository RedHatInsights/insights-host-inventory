"""Tests for host-ingestion sampling selection in inv_mq_service."""

import pytest

from app.telemetry import OTEL_HOST_INGESTION_SAMPLING_RATE


@pytest.mark.parametrize(
    ("consumer_topic", "ingress_topic", "expected"),
    [
        ("platform.inventory.host-ingress", "platform.inventory.host-ingress", OTEL_HOST_INGESTION_SAMPLING_RATE),
        ("platform.inventory.system-profile", "platform.inventory.host-ingress", None),
    ],
)
def test_sampling_rate_selection_by_topic(consumer_topic, ingress_topic, expected):
    """Host-ingress topic gets explicit sampling rate; others get None (env default)."""
    is_host_ingestion = consumer_topic == ingress_topic
    result = OTEL_HOST_INGESTION_SAMPLING_RATE if is_host_ingestion else None
    assert result == expected
