# ruff: noqa: ARG002
from unittest.mock import Mock
from unittest.mock import patch

from app.payload_tracker import NullProducer
from app.queue.event_producer import NullEventProducer
from app.queue.event_producer import create_event_producer
from app.queue.host_mq import NullConsumer
from app.queue.host_mq import create_consumer


class TestNullConsumer:
    """Test cases for NullConsumer class"""

    def test_null_consumer_initialization(self):
        """Test that NullConsumer initializes correctly"""
        config = Mock()
        config.replica_namespace = True

        consumer = NullConsumer(config)

        assert consumer.config == config

    def test_null_consumer_consume_returns_empty_list(self):
        """Test that consume method returns empty list"""
        config = Mock()
        consumer = NullConsumer(config)

        result = consumer.consume(num_messages=10, timeout=5.0)

        assert result == []

    def test_null_consumer_consume_with_default_parameters(self):
        """Test that consume method works with default parameters"""
        config = Mock()
        consumer = NullConsumer(config)

        result = consumer.consume()

        assert result == []

    def test_null_consumer_subscribe_does_nothing(self):
        """Test that subscribe method doesn't perform any action"""
        config = Mock()
        consumer = NullConsumer(config)
        topics = ["topic1", "topic2"]

        # Should not raise any exception
        consumer.subscribe(topics)

    def test_null_consumer_close_does_nothing(self):
        """Test that close method doesn't perform any action"""
        config = Mock()
        consumer = NullConsumer(config)

        # Should not raise any exception
        consumer.close()


class TestNullProducer:
    """Test cases for NullProducer class"""

    def test_null_producer_produce_logs_message(self, capsys):
        """Test that produce method prints the message"""
        producer = NullProducer()
        topic = "test-topic"
        msg = "test-message"

        producer.produce(topic, msg)

        captured = capsys.readouterr()
        assert f"sending message: {topic} - {msg}" in captured.out

    def test_null_producer_poll_does_nothing(self):
        """Test that poll method does nothing"""
        producer = NullProducer()

        # Should not raise any exception
        producer.poll(timeout=1.0)
        producer.poll()  # With default timeout


class TestNullEventProducer:
    """Test cases for NullEventProducer class"""

    def test_null_event_producer_initialization(self):
        """Test that NullEventProducer initializes correctly"""
        config = Mock()
        topic = "test-topic"

        producer = NullEventProducer(config, topic)

        assert producer.mq_topic == topic

    def test_null_event_producer_write_event_does_nothing(self):
        """Test that write_event method doesn't perform any action"""
        config = Mock()
        topic = "test-topic"
        producer = NullEventProducer(config, topic)

        event = "test-event"
        key = "test-key"
        headers = {"header1": "value1"}

        # Should not raise any exception
        producer.write_event(event, key, headers, wait=True)

    def test_null_event_producer_write_event_without_wait(self):
        """Test that write_event method works without wait parameter"""
        config = Mock()
        topic = "test-topic"
        producer = NullEventProducer(config, topic)

        event = "test-event"
        key = "test-key"
        headers = {"header1": "value1"}

        # Should not raise any exception
        producer.write_event(event, key, headers)

    def test_null_event_producer_close_does_nothing(self):
        """Test that close method doesn't perform any action"""
        config = Mock()
        topic = "test-topic"
        producer = NullEventProducer(config, topic)

        # Should not raise any exception
        producer.close()


class TestFactoryFunctions:
    """Test cases for factory functions that create null implementations"""

    def test_create_consumer_returns_null_consumer_when_replica_namespace(self):
        """Test that create_consumer returns NullConsumer when replica_namespace is True"""
        config = Mock()
        config.replica_namespace = True
        config.host_ingress_consumer_group = "test-group"
        config.bootstrap_servers = "localhost:9092"
        config.kafka_consumer = {}

        consumer = create_consumer(config)

        assert isinstance(consumer, NullConsumer)
        assert consumer.config == config

    def test_create_consumer_returns_real_consumer_when_not_replica_namespace(self):
        """Test that create_consumer returns real Consumer when replica_namespace is False"""
        config = Mock()
        config.replica_namespace = False
        config.host_ingress_consumer_group = "test-group"
        config.bootstrap_servers = "localhost:9092"
        config.kafka_consumer = {}

        with patch("app.queue.host_mq.Consumer") as mock_consumer_class:
            mock_consumer = Mock()
            mock_consumer_class.return_value = mock_consumer

            consumer = create_consumer(config)

            assert consumer == mock_consumer
            mock_consumer_class.assert_called_once_with(
                {
                    "group.id": "test-group",
                    "bootstrap.servers": "localhost:9092",
                    "auto.offset.reset": "earliest",
                    **config.kafka_consumer,
                }
            )

    def test_create_event_producer_returns_null_producer_when_replica_namespace(self):
        """Test that create_event_producer returns NullEventProducer when replica_namespace is True"""
        config = Mock()
        config.replica_namespace = True
        topic = "test-topic"

        producer = create_event_producer(config, topic)

        assert isinstance(producer, NullEventProducer)
        assert producer.mq_topic == topic

    def test_create_event_producer_returns_real_producer_when_not_replica_namespace(self):
        """Test that create_event_producer returns EventProducer when replica_namespace is False"""
        config = Mock()
        config.replica_namespace = False
        config.bootstrap_servers = "localhost:9092"
        config.kafka_producer = {}
        topic = "test-topic"

        with patch("app.queue.event_producer.EventProducer") as mock_producer_class:
            mock_producer = Mock()
            mock_producer_class.return_value = mock_producer

            producer = create_event_producer(config, topic)

            assert producer == mock_producer
            mock_producer_class.assert_called_once_with(config, topic)


class TestNullConsumerIntegration:
    """Integration tests for NullConsumer with HBIMessageConsumerBase"""

    def test_null_consumer_in_event_loop_returns_empty_messages(self, mocker):
        """Test that NullConsumer works correctly in the event loop context"""
        from app.queue.host_mq import HBIMessageConsumerBase

        # Mock the consumer
        config = Mock()
        config.replica_namespace = True
        null_consumer = NullConsumer(config)

        # Mock flask app and other dependencies
        flask_app = Mock()
        flask_app.app = Mock()
        flask_app.app.app_context = Mock()
        flask_app.app.app_context.return_value.__enter__ = Mock()
        flask_app.app.app_context.return_value.__exit__ = Mock()
        event_producer = Mock()
        notification_event_producer = Mock()

        # Create a concrete implementation of HBIMessageConsumerBase for testing
        class TestConsumer(HBIMessageConsumerBase):
            def process_message(self, *args, **kwargs):
                return None, None, None, None

            def handle_message(self, *args, **kwargs):
                return None

        consumer = TestConsumer(null_consumer, flask_app, event_producer, notification_event_producer)

        # Mock the interrupt function to return True after first iteration
        interrupt = mocker.Mock(side_effect=[False, True])

        # Mock inventory_config
        mock_config = Mock()
        mock_config.mq_db_batch_max_messages = 10
        mock_config.mq_db_batch_max_seconds = 1.0
        mocker.patch("app.queue.host_mq.inventory_config", return_value=mock_config)

        # Mock session_guard and db.session
        mock_session = Mock()
        mock_session.no_autoflush = Mock()
        mocker.patch("app.queue.host_mq.db.session", mock_session)
        mocker.patch("app.queue.host_mq.session_guard", return_value=Mock())

        # This should not raise any exceptions and should exit cleanly
        consumer.event_loop(interrupt)

        # The test passes if no exception is raised
        # The NullConsumer.consume method returns an empty list, which is the expected behavior


class TestNullProducerIntegration:
    """Integration tests for NullProducer with payload tracker"""

    def test_null_producer_with_payload_tracker(self, mocker):
        """Test that NullProducer works correctly with payload tracker"""
        from app.payload_tracker import get_payload_tracker

        # Mock config
        config = Mock()
        config.payload_tracker_enabled = True
        config.replica_namespace = True
        config.payload_tracker_kafka_topic = "test-topic"
        config.payload_tracker_service_name = "test-service"

        # Mock the producer
        null_producer = NullProducer()

        # Mock init_payload_tracker
        mocker.patch("app.payload_tracker._CFG", config)
        mocker.patch("app.payload_tracker._PRODUCER", null_producer)

        # Get payload tracker
        tracker = get_payload_tracker(request_id="test-request-id")

        # Should be a NullPayloadTracker when replica_namespace is True
        from app.payload_tracker import NullPayloadTracker

        assert isinstance(tracker, NullPayloadTracker)

        # All methods should not raise exceptions
        tracker.payload_received("test")
        tracker.payload_success("test")
        tracker.payload_error("test")
        tracker.processing("test")
        tracker.processing_success("test")
        tracker.processing_error("test")

        # inventory_id property should work
        tracker.inventory_id = "test-id"
        assert tracker.inventory_id is None  # NullPayloadTracker returns None


class TestNullEventProducerIntegration:
    """Integration tests for NullEventProducer with message consumers"""

    def test_null_event_producer_with_message_consumer(self, mocker):
        """Test that NullEventProducer works correctly with message consumers"""
        from app.queue.host_mq import IngressMessageConsumer

        # Mock config
        config = Mock()
        config.replica_namespace = True

        # Create null event producer
        null_producer = NullEventProducer(config, "test-topic")

        # Mock consumer
        mock_consumer = Mock()

        # Mock flask app
        flask_app = Mock()

        # Create message consumer with null event producer
        # Note: Using type: ignore because NullEventProducer is compatible with EventProducer interface
        consumer = IngressMessageConsumer(mock_consumer, flask_app, null_producer, null_producer)

        # Verify that the null producer is used
        assert consumer.event_producer == null_producer
        assert consumer.notification_event_producer == null_producer

        # Test that write_event doesn't raise exceptions
        null_producer.write_event("test-event", "test-key", {"header": "value"})
        null_producer.close()


class TestNullImplementationsEdgeCases:
    """Test edge cases and error conditions for null implementations"""

    def test_null_consumer_with_none_config(self):
        """Test NullConsumer with None config"""
        consumer = NullConsumer(None)
        assert consumer.config is None

        # Should still work without errors
        result = consumer.consume()
        assert result == []

        consumer.subscribe(["topic"])
        consumer.close()

    def test_null_producer_with_none_values(self, capsys):
        """Test NullProducer with None values"""
        producer = NullProducer()

        producer.produce(None, None)
        captured = capsys.readouterr()
        assert "sending message: None - None" in captured.out

        producer.poll(0.0)  # Use 0.0 instead of None for timeout

    def test_null_event_producer_with_none_values(self):
        """Test NullEventProducer with None values"""
        config = Mock()
        producer = NullEventProducer(config, None)

        # Should not raise any exception
        producer.write_event(None, None, None)

    def test_null_consumer_multiple_calls(self):
        """Test that NullConsumer can be called multiple times without issues"""
        config = Mock()
        consumer = NullConsumer(config)

        # Multiple consume calls
        for i in range(5):
            result = consumer.consume(num_messages=i, timeout=float(i))
            assert result == []

        # Multiple subscribe calls
        topics_list = [["topic1"], ["topic2", "topic3"], []]
        for topics in topics_list:
            consumer.subscribe(topics)

        # Multiple close calls
        for _ in range(3):
            consumer.close()

    def test_null_producer_multiple_calls(self, capsys):
        """Test that NullProducer can be called multiple times without issues"""
        producer = NullProducer()

        # Multiple produce calls
        for i in range(5):
            producer.produce(f"topic{i}", f"message{i}")

        # Multiple poll calls
        for i in range(3):
            producer.poll(timeout=float(i))

        captured = capsys.readouterr()
        for i in range(5):
            assert f"sending message: topic{i} - message{i}" in captured.out
