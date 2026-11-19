# HBI audit logging

Use `app.audit` for SEC-MON-REQ-1 operation results. The default configuration
emits one JSON record per line to stdout through `inventory.audit` at INFO.
Custom `INVENTORY_LOGGING_CONFIG_FILE` configurations must retain the audit logger,
handler and formatter.

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
