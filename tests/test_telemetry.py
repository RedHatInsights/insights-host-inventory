"""Tests for OpenTelemetry helpers in app.telemetry."""

from unittest.mock import MagicMock

from app.telemetry import _outbound_request_hook


def test_outbound_request_hook_updates_span_name():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "GET"
    request.path_url = "/api/client/features"

    _outbound_request_hook(span, request)

    span.update_name.assert_called_once_with("GET /api/client/features")


def test_outbound_request_hook_noop_when_not_recording():
    span = MagicMock()
    span.is_recording.return_value = False
    request = MagicMock()

    _outbound_request_hook(span, request)

    span.update_name.assert_not_called()


def test_outbound_request_hook_uses_slash_when_path_empty():
    span = MagicMock()
    span.is_recording.return_value = True
    request = MagicMock()
    request.method = "GET"
    request.path_url = ""

    _outbound_request_hook(span, request)

    span.update_name.assert_called_once_with("GET /")
