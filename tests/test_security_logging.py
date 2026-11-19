"""Exercise real security rejections without a database or external services."""

import asyncio
import json
from base64 import b64encode
from types import SimpleNamespace
from unittest.mock import Mock

import connexion
import pytest
from connexion.middleware import MiddlewarePosition
from connexion.options import SwaggerUIOptions
from connexion.resolver import Resolver
from flask import abort
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

from app import render_exception
from app import telemetry
from app.auth.rbac import KesselResourceTypes
from app.auth.rbac import RbacPermission
from app.auth.rbac import RbacResourceType
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import threadctx
from app.queue import export_service
from app.queue import export_service_mq
from app.queue.host_mq import IngressMessageConsumer
from app.security_logging import SecurityAuditMiddleware
from app.tags_blueprint import tags_bp
from lib import middleware
from lib import views_repository
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY

pytestmark = pytest.mark.usefixtures("restore_thread_context")

HOST_ID = "e3f9b2dd-1c8b-4d89-8b89-2ff9d8dc7cc4"
EXPORT_ID = "b462eb1b-2bea-4efc-84fd-5f2c911b211b"


def encoded_identity(data):
    return b64encode(json.dumps({"identity": data}).encode()).decode()


def headers(data=USER_IDENTITY):
    return {"x-rh-identity": encoded_identity(data), "x-rh-insights-request-id": "request-a"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(middleware, "inventory_config", lambda: SimpleNamespace(bypass_rbac=False))
    monkeypatch.setattr(middleware, "get_flag_value", lambda *args: False)
    monkeypatch.setattr(middleware, "is_rbac_v2_enabled", lambda _org_id: False)
    monkeypatch.setattr(middleware, "get_rbac_filter", lambda *args: (False, None))
    monkeypatch.setattr(middleware, "_build_rbac_request_headers", dict)
    monkeypatch.setattr(middleware, "resolve_permission", lambda *args, **kwargs: (False, None))
    monkeypatch.setattr(middleware, "_check_resource_exists", lambda *args: False)

    def denied():
        abort(403, "Existing denial response")

    @middleware.rbac(RbacResourceType.GROUPS, RbacPermission.READ)
    def rbac_denied():
        return {"unexpected": True}

    @middleware.access(KesselResourceTypes.HOST.view, "host_id")
    def concealed(host_id):
        return {"unexpected": host_id}

    handlers = {
        "allowed": lambda: {"ok": True},
        "denied": denied,
        "rbac_denied": rbac_denied,
        "concealed": concealed,
        "not_found": lambda: abort(404),
    }
    paths = {}
    for name in handlers:
        path = "/hosts/{host_id}" if name == "concealed" else "/" + name
        operation = {"operationId": name, "responses": {"default": {"description": "Unchanged response"}}}
        if name == "concealed":
            operation["parameters"] = [
                {"name": "host_id", "in": "path", "required": True, "schema": {"type": "string"}}
            ]
        paths[path] = {"get": operation}
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Security audit tests", "version": "1"},
        "paths": paths,
        "security": [{"identity": []}, {"bearer": []}],
        "components": {
            "securitySchemes": {
                "identity": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "x-rh-identity",
                    "x-apikeyInfoFunc": "app.auth.authentication_header_handler",
                },
                "bearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "x-bearerInfoFunc": "app.auth.bearer_token_handler",
                },
            }
        },
    }
    app = connexion.FlaskApp(__name__, swagger_ui_options=SwaggerUIOptions(serve_spec=False))
    app.add_middleware(SecurityAuditMiddleware, position=MiddlewarePosition.BEFORE_EXCEPTION)
    app.add_api(spec, resolver=Resolver(lambda operation_id: handlers[operation_id]))
    app.app.register_error_handler(InventoryException, render_exception)
    app.app.register_blueprint(tags_bp)
    return app.test_client()


@pytest.mark.parametrize(
    "credentials",
    [
        {},
        {"x-rh-identity": "invalid-credential-secret"},
        {"x-rh-identity": encoded_identity({"org_id": "untrusted-org", "user": {"user_id": "untrusted-user"}})},
        {"Authorization": "Bearer invalid-credential-secret"},
        {"Authorization": "Malformed credential-secret"},
    ],
)
def test_framework_authentication_rejections_emit_one_safe_event(client, audit_output, credentials):
    response = client.get(
        "/allowed?token=query-secret", headers={**credentials, "x-rh-insights-request-id": "request-a"}
    )

    assert response.status_code == 401
    events = [json.loads(line) for line in audit_output.getvalue().splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["action"] == "AUTHENTICATE"
    assert event["resource_id"] == "/allowed"
    assert event["outcome"] == "failure"
    assert event["principal"] is None
    assert event["org_id"] is None
    assert event["request_id"] == "request-a"
    assert event["reason"] == ("invalid_credentials" if credentials else "missing_credentials")
    assert "secret" not in audit_output.getvalue()
    assert "untrusted" not in audit_output.getvalue()


def test_http_authorization_rejection_preserves_verified_actor_and_response(client, audit_output):
    response = client.get("/denied?token=query-secret", headers=headers())

    assert response.status_code == 403
    assert response.json()["detail"] == "Existing denial response"
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "GET"
    assert event["resource_type"] == "http_request"
    assert event["resource_id"] == "/denied"
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["request_id"] == "request-a"
    assert event["reason"] == "permission_denied"
    assert "secret" not in audit_output.getvalue()


def test_rbac_rejection_emits_one_event(client, audit_output):
    path = "/rbac_denied"
    assert client.get(path, headers=headers()).status_code == 403
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]
    assert event["resource_id"] == path
    assert event["reason"] == "permission_denied"


def test_permission_denial_concealed_as_404_is_audited(client, audit_output):
    response = client.get("/hosts/" + HOST_ID, headers=headers())

    assert response.status_code == 404
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "GET"
    assert event["resource_type"] == "host"
    assert event["resource_id"] == HOST_ID
    assert event["reason"] == "permission_denied"
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]


def test_existing_resource_denial_is_audited_once(client, audit_output, monkeypatch):
    monkeypatch.setattr(middleware, "_check_resource_exists", lambda *args: True)
    assert client.get("/hosts/" + HOST_ID, headers=headers()).status_code == 403
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["resource_id"] == "/hosts/" + HOST_ID
    assert event["reason"] == "permission_denied"


def test_valid_shared_secret_rejection_does_not_invent_actor_or_tenant(client, audit_output, monkeypatch):
    monkeypatch.setenv("INVENTORY_SHARED_SECRET", "verified-credential-secret")
    response = client.get("/denied", headers={"Authorization": "Bearer verified-credential-secret"})
    assert response.status_code == 403
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["principal"] is None
    assert event["principal_type"] == "TrustedSystem"
    assert event["org_id"] is None
    assert "secret" not in audit_output.getvalue()


@pytest.mark.parametrize("sampled", [True, False])
@pytest.mark.parametrize("incoming_trace", [True, False])
def test_http_denial_retains_flask_server_trace(
    client, audit_output, otel_provider, monkeypatch, sampled, incoming_trace
):
    _, exporter = otel_provider(set_global=True, sampler=ALWAYS_ON if sampled else ALWAYS_OFF)
    monkeypatch.setattr(telemetry, "OTEL_ENABLED", True)
    monkeypatch.setattr(telemetry, "OTEL_HTTP_INBOUND_ENABLED", True)
    telemetry.instrument_flask_app(client.app)
    request_headers = headers()
    if incoming_trace:
        request_headers["traceparent"] = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    response = client.get("/denied", headers=request_headers)
    assert response.status_code == 403
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    spans = exporter.get_finished_spans()
    assert event["trace_id"] is not None
    assert event["span_id"] is not None
    if incoming_trace:
        assert event["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert event["span_id"] != "1234567890abcdef"  # remote parent is not the local span
    if sampled:
        assert len(spans) == 1
        assert event["trace_id"] == f"{spans[0].context.trace_id:032x}"
        assert event["span_id"] == f"{spans[0].context.span_id:016x}"
    else:
        assert spans == ()


@pytest.mark.parametrize(
    "traceparent,trace_id",
    [
        ("00-1234567890abcdef1234567890abcdef-1234567890abcdef-01", "1234567890abcdef1234567890abcdef"),
        ("invalid-trace-secret", None),
    ],
)
def test_pre_flask_auth_failure_preserves_valid_remote_trace_only(client, audit_output, traceparent, trace_id):
    assert client.get("/allowed", headers={"traceparent": traceparent}).status_code == 401
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["trace_id"] == trace_id
    assert event["span_id"] is None
    assert event["principal"] is None
    assert "secret" not in audit_output.getvalue()


def test_late_response_denial_retains_actor_context(client, audit_output):
    @client.app.app.after_request
    def reject(response):
        response.status_code = 403
        return response

    assert client.get("/allowed", headers=headers()).status_code == 403
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["principal"] == USER_IDENTITY["user"]["user_id"]
    assert event["request_id"] == "request-a"


@pytest.mark.parametrize("path,status", [("/allowed", 200), ("/not_found", 404)])
def test_success_and_ordinary_not_found_do_not_emit_denial(client, audit_output, path, status):
    assert client.get(path, headers=headers()).status_code == status
    assert audit_output.getvalue() == ""


def test_accepted_alternative_security_scheme_does_not_emit_false_failure(client, audit_output):
    assert (
        client.get("/allowed", headers={**headers(), "Authorization": "Bearer invalid-credential-secret"}).status_code
        == 200
    )
    assert audit_output.getvalue() == ""


def test_later_unauthenticated_request_does_not_reuse_previous_actor(client, audit_output):
    assert client.get("/denied", headers=headers()).status_code == 403
    assert client.get("/allowed").status_code == 401
    first, second = map(json.loads, audit_output.getvalue().splitlines())
    assert first["principal"] == USER_IDENTITY["user"]["user_id"]
    assert second["principal"] is None
    assert second["org_id"] is None
    assert second["request_id"] is None


@pytest.mark.parametrize("credentials", [{}, {"x-rh-identity": "invalid-credential-secret"}])
def test_bulk_tag_identity_failure_is_audited_without_changing_response(client, audit_output, credentials):
    response = client.post("/tags", json={"tags": ["tag"], "host_id_list": [HOST_ID]}, headers=credentials)

    assert response.status_code == 500
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "AUTHENTICATE"
    assert event["principal"] is None
    assert event["reason"] == "invalid_credentials"
    assert "secret" not in audit_output.getvalue()


def test_non_http_scope_passes_through_without_audit(audit_output):
    received = []

    async def downstream(scope, _receive, _send):
        received.append(scope["type"])

    asyncio.run(SecurityAuditMiddleware(downstream)({"type": "lifespan"}, None, None))
    assert received == ["lifespan"]
    assert audit_output.getvalue() == ""


def export_payload(identity=USER_IDENTITY, filters=None):
    return {
        "data": {
            "resource_request": {
                "format": "json",
                "export_request_uuid": EXPORT_ID,
                "application": "urn:redhat:application:inventory",
                "uuid": HOST_ID,
                "x_rh_identity": encoded_identity(identity),
                "filters": filters or {},
            }
        }
    }


def test_export_invalid_identity_has_safe_correlated_failure(audit_output):
    payload = export_payload()
    payload["data"]["resource_request"]["x_rh_identity"] = "invalid-credential-secret"
    with pytest.raises(ValueError):
        export_service.create_export(payload, SimpleNamespace())
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["resource_type"] == "export"
    assert event["resource_id"] == EXPORT_ID
    assert event["request_id"] == EXPORT_ID
    assert event["principal"] is None
    assert "secret" not in audit_output.getvalue()


@pytest.mark.parametrize("rejection", ["permission", "view_permission"])
def test_export_authorization_rejections_emit_one_event(audit_output, monkeypatch, rejection):
    payload = export_payload(USER_IDENTITY, {"view_id": HOST_ID} if rejection == "view_permission" else None)
    config = SimpleNamespace(
        export_service_endpoint="https://export.invalid", export_service_endpoint_ca_certificate=None
    )
    session = Mock()
    monkeypatch.setattr(export_service, "Session", lambda: session)
    monkeypatch.setattr(export_service, "build_headers", lambda *args: ({}, {}))
    monkeypatch.setattr(
        export_service, "resolve_permission", lambda *args, **kwargs: (rejection != "permission", None)
    )
    if rejection == "view_permission":
        monkeypatch.setattr(
            export_service, "_load_view_config", Mock(side_effect=views_repository.ViewPermissionError("Denied"))
        )
    error_handler = Mock()
    monkeypatch.setattr(export_service, "_handle_export_error", error_handler)

    assert export_service.create_export(payload, config) is False
    error_handler.assert_called_once()
    assert error_handler.call_args.args[1] == 403
    session.close.assert_called_once()
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "EXPORT"
    assert event["resource_id"] == EXPORT_ID
    assert event["request_id"] == EXPORT_ID
    assert event["org_id"] == USER_IDENTITY["org_id"]
    assert event["reason"] == "permission_denied"


@pytest.mark.parametrize(
    "invalid_identity",
    [
        "invalid-credential-secret",
        b64encode(b"[]").decode(),
        b64encode(b"null").decode(),
        b64encode(b'{"identity": []}').decode(),
    ],
)
def test_ingestion_invalid_identity_is_audited_without_trusting_tenant(audit_output, invalid_identity):
    consumer = object.__new__(IngressMessageConsumer)
    threadctx.request_id = "ingestion-a"
    threadctx.org_id = "previous-org"
    with pytest.raises((ValidationException, ValueError, TypeError, AttributeError)):
        consumer.process_message(
            {"org_id": "untrusted-org", "reporter": "puptoo", "system_profile": {}},
            {"b64_identity": invalid_identity},
        )
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "AUTHENTICATE"
    assert event["resource_type"] == "host_ingestion"
    assert event["org_id"] is None
    assert event["principal"] is None
    assert event["request_id"] == "ingestion-a"
    assert "secret" not in audit_output.getvalue()
    assert "untrusted-org" not in audit_output.getvalue()


def test_ingestion_owner_mismatch_preserves_verified_system_actor(audit_output, monkeypatch):
    consumer = object.__new__(IngressMessageConsumer)
    monkeypatch.setattr(
        "app.queue.host_mq.deserialize_host",
        lambda *args: SimpleNamespace(
            id=HOST_ID,
            static_system_profile=SimpleNamespace(owner_id="another-owner"),
        ),
    )
    threadctx.request_id = "ingestion-a"
    with pytest.raises(ValidationException):
        consumer.process_message(
            {"org_id": SYSTEM_IDENTITY["org_id"], "reporter": "puptoo", "system_profile": {}},
            {"b64_identity": encoded_identity(SYSTEM_IDENTITY)},
        )
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "INGEST"
    assert event["principal"] == SYSTEM_IDENTITY["system"]["cn"]
    assert event["org_id"] == SYSTEM_IDENTITY["org_id"]
    assert event["reason"] == "owner_mismatch"


@pytest.mark.parametrize("credential", [None, 123, [], "missing"])
def test_export_schema_credential_rejection_is_audited(audit_output, credential):
    payload = export_payload()
    resource = payload["data"]["resource_request"]
    resource["x-rh-identity"] = credential
    resource.pop("x_rh_identity")
    resource["resource"] = "hosts"
    if credential == "missing":
        del resource["x-rh-identity"]
    payload.update(
        {
            "id": HOST_ID,
            "source": export_service_mq.EXPORT_EVENT_SOURCE,
            "subject": "test",
            "specversion": "1.0",
            "type": "test",
            "time": "2026-11-18T12:00:00Z",
            "redhatorgid": "untrusted-org",
            "dataschema": "test",
        }
    )
    with pytest.raises(export_service_mq.ValidationError):
        export_service_mq.parse_export_service_message(json.dumps(payload))
    (event,) = map(json.loads, audit_output.getvalue().splitlines())
    assert event["action"] == "AUTHENTICATE"
    assert event["resource_type"] == "export"
    assert event["resource_id"] == EXPORT_ID
    assert event["request_id"] == EXPORT_ID
    assert event["principal"] is None
    assert event["org_id"] is None
    assert "untrusted-org" not in audit_output.getvalue()


@pytest.mark.parametrize("case", ["other_app", "other_source", "unrelated_schema"])
def test_unrelated_export_schema_rejection_is_not_authentication_failure(audit_output, case):
    payload = export_payload()
    resource = payload["data"]["resource_request"]
    resource["x-rh-identity"] = resource.pop("x_rh_identity")
    resource["resource"] = "hosts"
    payload.update(
        {
            "id": HOST_ID,
            "source": export_service_mq.EXPORT_EVENT_SOURCE,
            "subject": "test",
            "specversion": "1.0",
            "type": "test",
            "time": "2026-11-18T12:00:00Z",
            "redhatorgid": "untrusted-org",
            "dataschema": "test",
        }
    )
    if case == "other_app":
        resource["application"] = "another-app"
        del resource["x-rh-identity"]
    elif case == "other_source":
        payload["source"] = "another-source"
        del resource["x-rh-identity"]
    else:
        del resource["format"]
    with pytest.raises(export_service_mq.ValidationError):
        export_service_mq.parse_export_service_message(json.dumps(payload))
    assert audit_output.getvalue() == ""
