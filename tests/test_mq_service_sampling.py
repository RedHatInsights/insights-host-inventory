"""Tests for host-ingestion sampling selection in inv_mq_service."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


def _mq_config(*, consumer_topic: str) -> MagicMock:
    mock_config = MagicMock()
    mock_config.kafka_consumer_topic = consumer_topic
    mock_config.host_ingress_topic = "platform.inventory.host-ingress"
    mock_config.system_profile_topic = "platform.inventory.system-profile"
    mock_config.workspaces_topic = "platform.inventory.workspaces"
    mock_config.workspaces_bulk_topic = "platform.inventory.workspaces-bulk"
    mock_config.host_app_data_topic = "platform.inventory.host-app-data"
    mock_config.metrics_port = 9999
    mock_config.event_topic = "platform.inventory.events"
    mock_config.notification_topic = "platform.notifications.ingress"
    return mock_config


@pytest.mark.parametrize(
    ("consumer_topic", "expected_sampling_rate", "consumer_cls"),
    [
        ("platform.inventory.host-ingress", 0.75, "inv_mq_service.IngressMessageConsumer"),
        ("platform.inventory.system-profile", None, "inv_mq_service.SystemProfileMessageConsumer"),
    ],
)
def test_mq_main_selects_sampling_rate_by_topic(consumer_topic, expected_sampling_rate, consumer_cls):
    mock_config = _mq_config(consumer_topic=consumer_topic)
    mock_app = MagicMock()
    mock_app.app.config = {"INVENTORY_CONFIG": mock_config}

    with (
        patch("inv_mq_service.create_app", return_value=mock_app),
        patch("inv_mq_service.init_otel") as mock_init_otel,
        patch("inv_mq_service.OTEL_HOST_INGESTION_SAMPLING_RATE", 0.75),
        patch("inv_mq_service.init_cache"),
        patch("inv_mq_service.start_http_server"),
        patch("inv_mq_service.create_consumer", return_value=MagicMock()),
        patch("inv_mq_service.create_event_producer"),
        patch("inv_mq_service.register_shutdown"),
        patch("inv_mq_service.ShutdownHandler") as mock_shutdown_cls,
        patch(consumer_cls) as mock_consumer_cls,
        patch("inv_mq_service.get_build_version", return_value="1.2.3"),
    ):
        mock_shutdown_cls.return_value = MagicMock()
        mock_consumer_cls.return_value = MagicMock()

        import inv_mq_service

        inv_mq_service.main()

        mock_init_otel.assert_called_once_with(
            service_name="host-inventory-mq",
            service_version="1.2.3",
            sampling_rate=expected_sampling_rate,
        )
