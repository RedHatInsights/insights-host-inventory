"""Tests for OpenTelemetry helpers in app.telemetry."""

from unittest.mock import MagicMock

from opentelemetry.util.http import parse_excluded_urls

from app.telemetry import _outbound_request_hook


def test_flask_excluded_urls_match_full_request_url():
    """Flask OTEL matches excluded_urls against the full URL, not path-only."""
    excluded = parse_excluded_urls(r"/health$,/metrics$,/version$")
    assert excluded.url_disabled("http://host-inventory-stage.svc:8080/health")
    assert excluded.url_disabled("http://localhost:8080/metrics")
    assert excluded.url_disabled("http://app/version")
    assert not excluded.url_disabled("http://host-inventory-stage.svc:8080/healthz")
    assert not excluded.url_disabled("http://localhost:8080/api/metrics/summary")


def test_outbound_request_hook_sets_span_name():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "GET"
    request.path_url = "https://insights-stage.example/api/client/features?flag=1"

    _outbound_request_hook(span, request)

    span.update_name.assert_called_once_with("GET /api/client/features")


def test_outbound_request_hook_path_only_url():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "POST"
    request.path_url = "/internal/rbac"

    _outbound_request_hook(span, request)

    span.update_name.assert_called_once_with("POST /internal/rbac")


def test_outbound_request_hook_skips_non_recording_span():
    span = MagicMock()
    span.is_recording.return_value = False
    request = MagicMock()

    _outbound_request_hook(span, request)

    span.update_name.assert_not_called()
