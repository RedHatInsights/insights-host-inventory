"""Audit HTTP security rejections, including failures before Flask dispatch."""

from dataclasses import replace

from connexion.lifecycle import ConnexionRequest
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

from app.audit import AuditContext
from app.audit import capture_audit_context
from app.audit import log_audit_event
from app.auth.identity import Identity

_AUDIT_TRACE_KEY = "hbi_security_audit_trace"


def _capture_context(request: ConnexionRequest, status: int) -> AuditContext:
    identity = request.context.get("user")
    if status == 401 or not isinstance(identity, Identity):
        identity = None
    return capture_audit_context(identity, request_id=request.headers.get("x-rh-insights-request-id"))


def snapshot_security_audit_trace(span: trace.Span | None, environ: dict) -> None:
    """Retain the server span at creation, even if dispatch later raises a denial.

    Called by the existing Flask OTel request hook, including for unsampled spans.
    No new span is created and no request payload or identity is decoded here.
    """
    scope = environ.get("asgi.scope")
    if scope is not None and span is not None:
        span_context = span.get_span_context()
        if span_context.is_valid:
            ConnexionRequest(scope).context[_AUDIT_TRACE_KEY] = span_context


class SecurityAuditMiddleware:
    """Observe final 401/403 responses without changing authentication or response behavior.

    Install before Connexion's exception middleware so framework rejections (including
    missing credentials) and endpoint responses share the same single audit boundary.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = ConnexionRequest(scope)
        # Establish the shared context before routers copy the ASGI scope.
        context = request.context
        audited = False

        async def audit_send(message: Message) -> None:
            nonlocal audited
            if message["type"] == "http.response.start" and message["status"] in (401, 403) and not audited:
                audited = True
                unauthenticated = message["status"] == 401
                audit_context = _capture_context(request, message["status"])
                if audit_context.trace_id is None:
                    server_span = context.get(_AUDIT_TRACE_KEY)
                    if isinstance(server_span, trace.SpanContext) and server_span.is_valid:
                        audit_context = replace(
                            audit_context,
                            trace_id=f"{server_span.trace_id:032x}",
                            span_id=f"{server_span.span_id:016x}",
                        )
                if audit_context.trace_id is None:
                    # Pre-Flask rejections have no local server span. Preserve a valid
                    # incoming W3C trace ID without pretending its parent span is local.
                    remote = trace.get_current_span(
                        TraceContextTextMapPropagator().extract(request.headers)
                    ).get_span_context()
                    if remote.is_valid:
                        audit_context = replace(audit_context, trace_id=f"{remote.trace_id:032x}")
                reason = "permission_denied"
                if unauthenticated:
                    has_credentials = request.headers.get("x-rh-identity") or request.headers.get("authorization")
                    reason = "invalid_credentials" if has_credentials else "missing_credentials"
                # SEC-MON-REQ-1 EOI-7/8: only verified identity and static reasons.
                log_audit_event(
                    action="AUTHENTICATE" if unauthenticated else scope["method"],
                    resource_type="http_request",
                    resource_id=scope["path"],
                    outcome="failure",
                    context=audit_context,
                    reason=reason,
                )
            await send(message)

        await self.app(scope, receive, audit_send)
