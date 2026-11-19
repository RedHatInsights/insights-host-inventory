"""Structured stdout audit events, using explicit snapshots of validated context."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from ipaddress import ip_address
from typing import Literal
from uuid import UUID

from flask import has_request_context
from flask import request
from opentelemetry import trace

from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.logging import get_logger

logger = get_logger("audit")

_SAFE_AUDIT_REASONS = frozenset(
    {
        "already_processed",
        "delete_failed",
        "export_failed",
        "export_headers_failed",
        "group_mutation_failed",
        "host_data_validation_failed",
        "host_not_found",
        "ingestion_failed",
        "invalid_credentials",
        "invalid_export_request",
        "invalid_host_data",
        "invalid_message",
        "missing_application_header",
        "missing_credentials",
        "mutation_failed",
        "no_data",
        "owner_mismatch",
        "permission_denied",
        "projection_write_failed",
        "publication_unavailable",
        "result_preparation_failed",
        "system_profile_update_failed",
        "tag_update_failed",
        "transaction_failed",
        "unknown_application",
        "unspecified_reason",
        "workspace_request_failed",
    }
)


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Capture before deferring work; never reconstruct an actor from thread-local state."""

    org_id: str | None = None
    principal: str | None = None
    principal_type: str | None = None
    request_id: str | None = None
    user_ip: str | None = None
    trace_id: str | None = None
    span_id: str | None = None


def capture_audit_context(
    identity: Identity | None = None,
    *,
    system_actor: str | None = None,
    org_id: str | None = None,
    request_id: str | None = None,
    user_ip: str | None = None,
) -> AuditContext:
    """Use a validated Identity or a known job/service name, never an unvalidated header.

    Pass org_id for automated/shared-secret operations and request_id for message work.
    user_ip must come from an agreed trusted source; no proxy header is trusted here.
    An org-only synthetic identity and a shared secret cannot identify a human/caller.
    """
    if identity is not None and system_actor is not None:
        raise ValueError("Specify either an identity or a system actor")

    principal = system_actor
    principal_type = "SystemActor" if system_actor else None
    if identity is not None:
        if identity.is_trusted_system:
            principal_type = "TrustedSystem"
        else:
            if org_id is not None and org_id != identity.org_id:
                raise ValueError("Audit organization must match the validated identity")
            org_id = identity.org_id
            match identity.identity_type:
                case IdentityType.USER:
                    user = getattr(identity, "user", {})
                    principal = user.get("user_id") or user.get("username")
                case IdentityType.SERVICE_ACCOUNT | IdentityType.ASSOCIATE:
                    principal = identity.service_account["client_id"]
                case IdentityType.SYSTEM:
                    principal = identity.system["cn"]
                case IdentityType.X509:
                    principal = identity.x509["subject_dn"]
            principal_type = identity.identity_type if principal else None

    if request_id is None and has_request_context():
        request_id = request.headers.get("x-rh-insights-request-id")
    span = trace.get_current_span().get_span_context()
    return AuditContext(
        org_id=org_id,
        principal=principal,
        principal_type=principal_type,
        request_id=request_id,
        user_ip=str(ip_address(user_ip)) if user_ip else None,
        trace_id=f"{span.trace_id:032x}" if span.is_valid else None,
        span_id=f"{span.span_id:016x}" if span.is_valid else None,
    )


class AuditFormatter(logging.Formatter):
    """Serialize only the audit contract, excluding arbitrary extras and exceptions."""

    def format(self, record: logging.LogRecord) -> str:
        fields = (
            "action",
            "resource_type",
            "resource_id",
            "outcome",
            "principal",
            "principal_type",
            "org_id",
            "request_id",
            "user_ip",
            "trace_id",
            "span_id",
            "reason",
        )
        event = {field: getattr(record, field, None) for field in fields}
        event.update(
            timestamp=datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            logger=record.name,
            level=record.levelname,
            message="Security audit event",
        )
        return json.dumps(event, separators=(",", ":"))


def log_audit_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str | UUID | None = None,
    outcome: Literal["success", "failure"],
    context: AuditContext,
    reason: str | None = None,
) -> None:
    """Emit an operation result; success belongs after commit/downstream acceptance.

    action/resource_type and optional reason must be static application vocabulary.
    Never pass bodies, credentials, raw identity headers or exception text.
    """
    # SEC-MON-REQ-1: shared fields for EOI-1/2/3/4/5/7/8/11 operation call sites.
    logger.info(
        "Security audit event",
        extra={
            **asdict(context),
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id is not None else None,
            "outcome": outcome,
            "reason": reason if reason is None or reason in _SAFE_AUDIT_REASONS else "unspecified_reason",
        },
    )
