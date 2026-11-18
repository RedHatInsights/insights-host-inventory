# HBI audit logging

Use `app.audit` for SEC-MON-REQ-1 operation results. The default configuration
emits one JSON record per line to stdout through `inventory.audit` at INFO.
Custom `INVENTORY_LOGGING_CONFIG_FILE` configurations must retain the audit logger,
handler and formatter.

## Authentication and authorization events

`SecurityAuditMiddleware` observes final HTTP 401/403 responses outside Connexion's
exception middleware, including missing/malformed credentials rejected before
Flask dispatch. A 401 emits `AUTHENTICATE`; a 403 uses the attempted HTTP method.
These events use `resource_type=http_request` and the request path as `resource_id`,
which identifies the attempted endpoint/resource without recording query strings,
credentials or bodies. A rejected identity never establishes a principal or tenant.
403 events use only an already validated `Identity` from Connexion's shared context.
Static reasons are `missing_credentials`, `invalid_credentials` or
`permission_denied`. A successfully authenticated alternative security scheme
does not produce a false failure event.

Known permission denials concealed as 404 by the `access` decorator are logged
explicitly with the known resource type/IDs. Ordinary 404s are not labeled as
permission denials. Direct handler failures (views, application-data filters,
group restrictions, enabled admin operations) are covered by the final 403
boundary; lower-level checks do not add duplicate audit events.

The existing Flask OTel request hook saves the real server span context before
dispatch/teardown, including unsampled spans. The final audit event reuses those
IDs even when Connexion renders a raised denial after the Flask span has ended.
For a pre-Flask failure with a valid W3C `traceparent`, the incoming trace ID is
retained for correlation; `span_id` stays null because no local span was created.
Malformed trace headers are ignored. Trace metadata is correlation, not identity.

Bulk-tag credential parsing, ingress identity/owner checks, and export identity,
permission and application-data restrictions emit explicit events because they
can bypass the OpenAPI HTTP boundary. Export schema credential failures are
audited only when validated source/application fields identify an HBI export;
only a validated export UUID is used for correlation. Invalid credentials leave
principal/tenant unknown. Existing message rejection behavior is preserved.

The bearer callback now raises Connexion's native authentication exception,
returning the intended 401 rather than letting a pre-Flask Werkzeug exception
become a 500. No credentials or raw authentication errors are added to audit output.

## Event fields

| Field | Meaning |
|---|---|
| `timestamp` | UTC emission time in ISO 8601 format. |
| `logger`, `level`, `message` | `inventory.audit`, `INFO`, and `Security audit event`. |
| `action`, `resource_type`, `resource_id` | Static operation name, resource kind and affected identifier; unknown identifiers are null. |
| `outcome` | `success` or `failure`, reflecting the actual result. |
| `principal`, `principal_type`, `org_id` | Validated actor and tenant, or an explicitly supplied system actor and tenant scope. Unknown values remain null. |
| `request_id` | HTTP `x-rh-insights-request-id` or explicit message correlation; no thread-local fallback. |
| `trace_id`, `span_id` | Active OTel context, independent of sampling; null when unavailable. |
| `user_ip` | Explicit original-user IP, normalized as IPv4/IPv6. Proxy headers are not read automatically. |
| `reason` | Optional allowlisted result code, such as `permission_denied`; unknown codes become `unspecified_reason`. |

## Usage

Capture the immutable context while the validated identity and original request
are available. Carry it with deferred work and emit success after commit.

```python
from app.audit import capture_audit_context
from app.audit import log_audit_event

context = capture_audit_context(current_identity)

# SEC-MON-REQ-1 EOI-1: emit after the host change commits.
log_audit_event(
    action="UPDATE",
    resource_type="host",
    resource_id=host_id,
    outcome="success",
    context=context,
)
```

Emit one record per committed host operation. No-ops and rolled-back work do not
produce mutation-success records. Log failures with `outcome="failure"` and a
safe static `reason`.

For jobs, use `capture_audit_context(system_actor="host-reaper", org_id=host_org_id)`.
For messages, pass the validated identity and explicit `request_id`. Omit the
identity for unauthenticated failures. Synthetic identities and shared secrets
do not establish an individual caller. Never include credentials or payloads.
