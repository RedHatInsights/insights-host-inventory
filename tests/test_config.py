import pytest

from app.config import Config
from app.environment import RuntimeEnvironment


@pytest.mark.parametrize("value", [0, 1, "all"])
def test_kafka_producer_acks(monkeypatch, value):
    monkeypatch.setenv("KAFKA_PRODUCER_ACKS", f"{value}")
    config = Config(RuntimeEnvironment.TEST)
    assert config.kafka_producer["acks"] == value


def test_kafka_producer_acks_unknown(monkeypatch):
    monkeypatch.setenv("KAFKA_PRODUCER_ACKS", "2")
    with pytest.raises(ValueError):
        Config(RuntimeEnvironment.TEST)


@pytest.mark.parametrize(
    "param", ["retries", "batch_size", "linger_ms", "retry_backoff_ms", "max_in_flight_requests_per_connection"]
)
def test_kafka_producer_int_params(monkeypatch, param):
    monkeypatch.setenv(f"KAFKA_PRODUCER_{param.upper()}", "2020")
    config = Config(RuntimeEnvironment.TEST)
    assert config.kafka_producer[param] == 2020


@pytest.mark.parametrize(
    "param", ["retries", "batch_size", "linger_ms", "retry_backoff_ms", "max_in_flight_requests_per_connection"]
)
def test_kafka_producer_int_params_invalid(monkeypatch, param):
    monkeypatch.setenv(f"KAFKA_PRODUCER_{param.upper()}", "abc")
    with pytest.raises(ValueError):
        Config(RuntimeEnvironment.TEST)
