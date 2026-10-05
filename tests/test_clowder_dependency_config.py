import os
from types import SimpleNamespace
from unittest.mock import patch

from app.config import Config
from app.config import _v1_dependency_endpoint_uri
from app.config import resolve_dependency_endpoint_settings
from app.environment import RuntimeEnvironment


class TestResolveDependencyEndpointSettings:
    def test_uses_v2_when_available(self):
        v2 = SimpleNamespace(uri="https://rbac:8443", ca_certificate="/ca.crt", authenticated=True)
        uri, ca, auth = resolve_dependency_endpoint_settings(
            v2,
            v1_uri="http://old:8080",
            v1_ca_certificate="/old.ca",
        )

        assert uri == "https://rbac:8443"
        assert ca == "/ca.crt"
        assert auth is True

    def test_falls_back_to_v1_when_v2_missing(self):
        uri, ca, auth = resolve_dependency_endpoint_settings(
            None,
            v1_uri="http://rbac:8080",
            v1_ca_certificate="/tls.ca",
        )

        assert uri == "http://rbac:8080"
        assert ca == "/tls.ca"
        assert auth is False

    def test_falls_back_to_v1_when_v2_uri_empty(self):
        v2 = SimpleNamespace(uri="", ca_certificate=None, authenticated=True)
        uri, ca, auth = resolve_dependency_endpoint_settings(
            v2,
            v1_uri="http://rbac:8080",
            v1_ca_certificate="/tls.ca",
        )

        assert uri == "http://rbac:8080"
        assert ca == "/tls.ca"
        assert auth is False


class TestV1DependencyEndpointUri:
    def test_builds_http_uri_without_tls(self):
        endpoint = SimpleNamespace(app="rbac", hostname="rbac.svc", port=8080, tlsPort=8443)

        assert _v1_dependency_endpoint_uri([endpoint], "rbac", None) == "http://rbac.svc:8080"

    def test_builds_https_uri_with_tls_ca(self):
        endpoint = SimpleNamespace(app="rbac", hostname="rbac.svc", port=8080, tlsPort=8443)

        assert _v1_dependency_endpoint_uri([endpoint], "rbac", "/ca.crt") == "https://rbac.svc:8443"

    def test_returns_empty_string_when_app_not_found(self):
        endpoint = SimpleNamespace(app="other", hostname="other.svc", port=8080, tlsPort=8443)

        assert _v1_dependency_endpoint_uri([endpoint], "rbac", None) == ""


class TestKafkaSslConfigs:
    def test_kafka_ssl_configs_plaintext(self):
        with patch.dict(os.environ, {"CLOWDER_ENABLED": "false", "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT"}):
            config = Config(RuntimeEnvironment.TEST)
            assert "sasl.mechanism" not in config.kafka_ssl_configs
            assert "sasl.username" not in config.kafka_ssl_configs
            assert "sasl.password" not in config.kafka_ssl_configs
            assert config.kafka_ssl_configs["security.protocol"] == "PLAINTEXT"

    def test_kafka_ssl_configs_sasl_ssl(self):
        with patch.dict(os.environ, {"CLOWDER_ENABLED": "false", "KAFKA_SECURITY_PROTOCOL": "SASL_SSL"}):
            config = Config(RuntimeEnvironment.TEST)
            assert "sasl.mechanism" in config.kafka_ssl_configs
            assert "sasl.username" in config.kafka_ssl_configs
            assert "sasl.password" in config.kafka_ssl_configs
            assert config.kafka_ssl_configs["security.protocol"] == "SASL_SSL"


def test_kafka_ssl_configs_ssl_omits_sasl():
    with patch.dict(os.environ, {"CLOWDER_ENABLED": "false", "KAFKA_SECURITY_PROTOCOL": "SSL"}):
        config = Config(RuntimeEnvironment.TEST)
        assert config.kafka_ssl_configs["security.protocol"] == "SSL"
        assert "sasl.mechanism" not in config.kafka_ssl_configs
        assert "sasl.username" not in config.kafka_ssl_configs
        assert "sasl.password" not in config.kafka_ssl_configs


def test_kafka_ssl_configs_sasl_plaintext_includes_sasl():
    with patch.dict(os.environ, {"CLOWDER_ENABLED": "false", "KAFKA_SECURITY_PROTOCOL": "SASL_PLAINTEXT"}):
        config = Config(RuntimeEnvironment.TEST)
        assert config.kafka_ssl_configs["security.protocol"] == "SASL_PLAINTEXT"
        assert "sasl.mechanism" in config.kafka_ssl_configs
        assert "sasl.username" in config.kafka_ssl_configs
        assert "sasl.password" in config.kafka_ssl_configs


def test_kafka_ssl_configs_default_protocol_omits_sasl():
    env_clean = {k: v for k, v in os.environ.items() if k != "KAFKA_SECURITY_PROTOCOL"}
    env_clean["CLOWDER_ENABLED"] = "false"
    with patch.dict(os.environ, env_clean, clear=True):
        config = Config(RuntimeEnvironment.TEST)
        assert config.kafka_ssl_configs["security.protocol"] == "PLAINTEXT"
        assert "sasl.mechanism" not in config.kafka_ssl_configs
        assert "sasl.username" not in config.kafka_ssl_configs
        assert "sasl.password" not in config.kafka_ssl_configs


def test_kafka_ssl_configs_sasl_custom_credentials():
    env = {
        "CLOWDER_ENABLED": "false",
        "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "KAFKA_SASL_USERNAME": "test-kafka-user",
        "KAFKA_SASL_PASSWORD": "test-kafka-password",
        "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
    }
    with patch.dict(os.environ, env):
        config = Config(RuntimeEnvironment.TEST)
        assert config.kafka_ssl_configs["security.protocol"] == "SASL_SSL"
        assert config.kafka_ssl_configs["sasl.mechanism"] == "SCRAM-SHA-512"
        assert config.kafka_ssl_configs["sasl.username"] == "test-kafka-user"
        assert config.kafka_ssl_configs["sasl.password"] == "test-kafka-password"


def test_kafka_ssl_configs_downstream_consumers_and_producers():
    with patch.dict(os.environ, {"CLOWDER_ENABLED": "false", "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT"}):
        config = Config(RuntimeEnvironment.TEST)
        for consumer_or_producer in (
            config.base_consumer_config,
            config.kafka_consumer,
            config.export_service_kafka_consumer,
            config.payload_tracker_kafka_producer,
        ):
            assert "sasl.mechanism" not in consumer_or_producer
            assert "sasl.username" not in consumer_or_producer
            assert "sasl.password" not in consumer_or_producer

    with patch.dict(os.environ, {"CLOWDER_ENABLED": "false", "KAFKA_SECURITY_PROTOCOL": "SASL_SSL"}):
        config = Config(RuntimeEnvironment.TEST)
        for consumer_or_producer in (
            config.base_consumer_config,
            config.kafka_consumer,
            config.export_service_kafka_consumer,
            config.payload_tracker_kafka_producer,
        ):
            assert "sasl.mechanism" in consumer_or_producer
            assert "sasl.username" in consumer_or_producer
            assert "sasl.password" in consumer_or_producer
