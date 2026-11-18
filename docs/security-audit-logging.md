# HBI audit logging

Use `app.audit` for SEC-MON-REQ-1 operation results. The default logging configuration
routes `inventory.audit` to one JSON record per line on stdout, at INFO, without
propagating to the diagnostic or direct CloudWatch handlers. Existing operational
logs keep their current formatting. Collector forwarding and Catalog queries are
separate onboarding work. A custom `INVENTORY_LOGGING_CONFIG_FILE` must retain the
audit logger, handler and formatter definitions.

This foundation does not yet instrument business operations. Those call sites,
including authentication/authorization failures, are subsequent work.

## Event dictionary

| Field | Meaning |
|---|---|
| `timestamp` | UTC emission time in ISO 8601 format. |
| `logger`, `level`, `message` | Logger identity, severity and fixed audit-event description. Use `logger = "inventory.audit"` to identify these records. |
| `action`, `resource_type`, `resource_id` | Static operation name, resource kind and affected identifier. An unavailable/not-applicable identifier is null. |
| `outcome` | `success` or `failure`, representing the actual operation result. |
| `principal`, `principal_type` | Validated actor identifier and its identity type. User: user ID, falling back to username; service account: client ID; system: certificate CN; X509: certificate subject DN; automated actor: a known job/service name with type `SystemActor`. |
| `org_id` | Organization from the validated identity, or explicitly supplied for system/shared-secret work. |
| `request_id` | Current HTTP request's `x-rh-insights-request-id`, or explicitly supplied message/request correlation. Outside HTTP, there is no thread-local fallback. |
| `trace_id`, `span_id` | Snapshot of the active OTel span, or null when unavailable. Logging does not depend on trace sampling. |
| `user_ip` | Explicitly supplied original user IP, normalized as IPv4/IPv6. No forwarded/proxy header is trusted automatically. |
| `reason` | Optional static, safe result code, such as `permission_denied`. Never an exception/parser message. |

Unknown fields remain null. A synthetic org-only identity does not become a human
principal. A valid shared secret establishes `principal_type = "TrustedSystem"`,
but identifies neither an individual caller nor a tenant; those fields remain null
unless tenant scope is supplied explicitly. Credentials and identity payloads are
never serialized. The formatter uses a field allowlist and omits exception text.

## Usage and deferred work

```python
from app.audit import capture_audit_context
from app.audit import log_audit_event

# Capture while the validated identity and original request/trace are available.
context = capture_audit_context(current_identity)

# Perform the operation and commit its transaction first.
# SEC-MON-REQ-1 EOI-1: customer host mutation.
log_audit_event(
    action="UPDATE",
    resource_type="host",
    resource_id=host_id,
    outcome="success",
    context=context,
)
```

Carry the immutable context with deferred results and emit it after the correct
transaction/result boundary. It is not refreshed from whichever request or message
happens to be current at emission time. For a job use
`capture_audit_context(system_actor="host-reaper", org_id=host_org_id)`; for message
processing pass the available validated identity and explicit `request_id`.
For unauthenticated failures capture without an identity; do not parse an invalid
header to invent a principal.

User-IP acquisition still needs an agreed trusted gateway contract. Until then,
leave it null rather than using the target host's address or trusting forwarded
headers. This is a remaining requirement for user-associated events, not an
exemption. High-volume/batch/no-op granularity, protected reads and access-change
applicability also remain owner/ProdSec decisions. Failed operations must use
safe static reasons and must not turn rolled-back work into successful audit events.
