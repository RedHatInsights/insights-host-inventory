# Spec: RHINENG-3926

## Summary
HBI complains about SASL config in ephemeral environments

## Root Cause
In `app/config.py`, the `Config` class unconditionally includes SASL configuration keys (`sasl.mechanism`, `sasl.username`, `sasl.password`) in `self.kafka_ssl_configs` even when the security protocol is set to `PLAINTEXT` (which is the default for classic Kafka ephemeral environments). When this configuration dictionary is passed to the `confluent-kafka` (rdkafka) client, rdkafka detects that `sasl.mechanism` is set to `PLAIN` but `security.protocol` is not configured for SASL, triggering a configuration warning in the logs.

## Plan

- `app/config.py` (modify): In `__init__`, change the construction of `self.kafka_ssl_configs` (around line 327) so that the three SASL keys (`sasl.mechanism`, `sasl.username`, `sasl.password`) are only included when `self.kafka_security_protocol` starts with `SASL_`. The base dictionary should always contain `security.protocol` and `ssl.ca.location`; the SASL entries should be conditionally added afterward.

- `tests/test_clowder_dependency_config.py` (modify): Add a new test class that verifies `kafka_ssl_configs` behavior. Add a test that creates a `Config` (non-Clowder, `RuntimeEnvironment.TEST`) with `KAFKA_SECURITY_PROTOCOL` set to `PLAINTEXT` and asserts that `sasl.mechanism`, `sasl.username`, and `sasl.password` are absent from `kafka_ssl_configs`. Add a second test with `KAFKA_SECURITY_PROTOCOL` set to `SASL_SSL` and asserts that all three SASL keys are present. Use `os.environ` patching (e.g., `unittest.mock.patch.dict`) to control the env vars, following the existing test patterns in the file.

## Constraints
- Must not break production/managed-Kafka environments where kafka_security_protocol is SASL_SSL — SASL keys must still be included in that case.
- kafka_ssl_configs is consumed only via dictionary unpacking; no code performs direct key access on the SASL entries.
