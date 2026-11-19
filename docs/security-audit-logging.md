# HBI audit logging

Use `app.audit` for SEC-MON-REQ-1 operation results. The default configuration
emits one JSON record per line to stdout through `inventory.audit` at INFO.
Custom `INVENTORY_LOGGING_CONFIG_FILE` configurations must retain the audit logger,
handler and formatter.

## Authentication and authorization

HTTP failures emit one record with `outcome="failure"`,
`resource_type="http_request"` and the request path as `resource_id`.
Query strings, headers and request bodies are excluded.

| Response | Action | Reason |
|---|---|---|
| 401 | `AUTHENTICATE` | `missing_credentials` or `invalid_credentials` |
| 403 | Attempted HTTP method | `permission_denied` |

401 records leave actor and tenant unknown; 403 records use an already validated
identity when available. Accepted alternative authentication schemes produce no
failure event. HTTP request/trace context is retained through final response handling.

Known permission denials concealed as 404 are logged explicitly with the requested
resource identifiers. Ordinary 404s are not permission-denial events.

Bulk-tag credential parsing, ingress identity/owner checks and export security
checks emit explicit events where they bypass the HTTP boundary. Export schema
credential failures are logged only for a validated HBI target, using a validated
export UUID for correlation when available.
Other identifiable HBI export schema failures emit `EXPORT` failures using only
validated target and actor fields.

## Host operations and transaction boundaries

Emit one individual audit record per committed host operation. Ingestion DB batches
keep separate records for each operation, including repeated operations on the same
host. Collector buffering/forwarding can batch those records without aggregating
their contents. Aggregation requires measured volume and an approved format that
preserves the required evidence; no sampling or aggregation is implemented here.

Measure records/second and average serialized bytes per resource type with a
representative workload, including reaper and membership changes. Daily uncompressed
GB is `records_per_second * average_record_bytes * 86400 / 1e9`; message counts alone
underestimate messages with multiple host operations. Use these measurements to
size forwarding and retention in [Phase 3 (RHINENG-33800)](https://issues.redhat.com/browse/RHINENG-33800).

| Operation | Action / resource type / identifier |
|---|---|
| Core ingress create/update | `CREATE` or `UPDATE` / `host` / persisted host UUID |
| Ingress rejection before its result is known | `INGEST` / `host` / resolved UUID when available, otherwise null |
| System-profile update | `UPDATE` / `host` / persisted host UUID |
| Host patch | `UPDATE` / `host` / host UUID |
| Explicit host check-in | `CHECK_IN` / `host` / host UUID |
| Replace/merge a facts namespace | `UPDATE` / `host_facts` / `host_UUID:namespace` |
| Bulk tags | `UPDATE` / `host_tags` / each changed host UUID |
| Delete by ID/filter/all, including callers of the shared deletion helper | `DELETE` / `host` / each deleted host UUID |

`AuditEvent` carries only scalar identifiers and an immutable context snapshot.
Capture it while the original request/message context is active, then emit success
after the applicable transaction commits. Patch/facts commit per changed host;
tags and deletes commit per chunk; ingestion commits its DB batch. Earlier chunks
remain successful if a later chunk rolls back. A no-op patch/tag/system-profile
update produces no mutation success event; the tag API's processed count still
includes unchanged hosts, but excludes rolled-back batches. Missing/foreign-tenant hosts do not become
successful changes. Bodies, facts values, tag values and display names are excluded.

Ingestion and patch/facts publish business events after DB commit. A later Kafka
publication failure does not turn the committed mutation into a database failure.
The deletion helper retains its existing pre-commit publication sequence; a failed
publication rolls back that chunk. Its results and success callbacks are released
after commit. This does not make DB/Kafka effects atomic or delivery exactly once.

Write/commit failures use static reasons (`mutation_failed`, `transaction_failed`,
`tag_update_failed`, `delete_failed`, `publication_unavailable`, `ingestion_failed`,
`system_profile_update_failed`, `result_preparation_failed`). A repository failure
before host resolution uses a null resource ID rather than the generated candidate
UUID, which may differ from a deduplicated host. Normalized system-profile errors
propagate into the message's savepoint. Ingress, system-profile and host-app
processing flush inside one savepoint per message: a permanent rejection rolls
back that message, discards its pending result and clears message-derived caches.
Healthy messages remain eligible for commit, publication and success records.
Rejected messages are acknowledged when the batch completes, including an entirely
rejected batch. The existing retryable DB errors still abort/retry the batch;
connection-level operational errors retain the existing restart behavior.
Workspace handlers retain their own per-message commits and rollbacks.
SIEM queries for ingestion failures must include `action=INGEST`; a rejection
before resolving a host cannot reliably be labeled `CREATE` or `UPDATE`.
For tags, a failed host's unflushed
state is expired so it cannot leak into the successful remainder of the chunk.

Validated originating identities are preserved per message. Identity-free RHSM
ingress uses `ingress-consumer`, and org-only system-profile processing uses
`system-profile-consumer`, both with `principal_type=SystemActor`. A deletion job
uses `host-delete:<control_rule>` (or `host-delete`) and the affected host's org.
No synthetic identity is presented as an authenticated user or host originator.
When message spans or MQ tracing are disabled, a valid incoming W3C trace ID is
still retained; `span_id` is null because there is no local message span. Missing
or invalid incoming trace context does not reuse an unrelated batch trace.

## Reaper

Reaper's existing `delete_hosts(..., control_rule="REAPER")` call emits one
`DELETE / host` record per committed host, with `principal=host-delete:REAPER`,
`principal_type=SystemActor`, the host UUID and its organization. These records
cover the customer mutation and privileged automated operation together. An empty
run produces no mutation record; no duplicate job-run audit record is added.
Interruption or a write/publication/commit failure rolls back the current chunk
and emits failures for its attempted hosts. Earlier committed chunks stay successful.
Graceful interruption uses reason `interrupted`; write failures use `delete_failed`.

The initial job scope covers reaper and existing callers of the shared deletion
helper. Direct writes in `create_ungrouped_host_groups.py` and
`assign_ungrouped_hosts_to_groups.py` are not instrumented by the API transaction
helpers. Their applicability and remaining mutation coverage are tracked in
[Phase 1 (RHINENG-33798)](https://issues.redhat.com/browse/RHINENG-33798);
this scope boundary is not a compliance exemption for those repair jobs.

The deletion helper locks the selected host rows through commit. Caller filters,
joins, grouping and chunk limits stay in a candidate subquery; the outer query
locks only the matching host rows by both host ID and organization. This supports
the grouped RBAC queries and retains ORM deletion/outbox hooks. It prevents another
transaction's removal from being reported as this process's successful deletion.
Competing writers wait for the chunk transaction; this adds no per-host SELECT.
It does not introduce DB/Kafka atomicity or redefine mutable eligibility predicates.

## Groups, workspaces, views and staleness

| Operation | Action / resource type / identifier |
|---|---|
| Local group create/update/delete | `CREATE`, `UPDATE`, `DELETE` / `group` / group UUID |
| Membership addition/removal/move | `CREATE` or `DELETE` / `group_membership` / `group_UUID:host_UUID` |
| Delegated RBAC request | `REQUEST_CREATE`, `REQUEST_UPDATE`, `REQUEST_DELETE` / `workspace_request` / workspace UUID when known |
| Saved view create/clone/update/delete | `CREATE`, `UPDATE`, `DELETE` / `saved_view` / affected view UUID (new clone UUID for clone) |
| Set/unset a default view | `SET_DEFAULT` or `DELETE` / `view_preference` / `org_id:user_id` |
| Custom staleness create/update/delete/reset | `CREATE`, `UPDATE`, `DELETE` / `staleness_policy` / organization ID |

`audit_operation` surrounds the commit owner (`session_guard` exits first), while
refresh, response serialization, Kafka publication and cache invalidation remain
outside. These later failures preserve the committed audit success. Rollback
emits only failures with static reasons. Denials remain at the existing HTTP
security boundary rather than adding duplicate mutation-denial records.

Group metadata events use this transaction's recorded inserts, deletes and name
changes; they need no before/after graph queries. Membership records come from
the rows this transaction deletes (SQL `RETURNING`/affected-row results) and the
associations it inserts, rather than observing another actor's before/after
state. Opposite changes within one transaction cancel; savepoint retries discard
their rolled-back records. Newly observed external workspace mirrors are not
claimed as locally created groups. Local automatic ungrouped-group creation is
recorded by the transaction that inserts it. Failed group operations identify
the attempted group scope with reason `group_mutation_failed`.

A successful `workspace_request` event means the RBAC call returned successfully;
it does not assert that the HBI mirror or later host changes committed. Errors
use `workspace_request_failed`; create requests without an ID fail with null ID.
Workspace messages identify the known `workspace-consumer` system actor, with
their tenant and available request/producer trace context. Create/update/delete
each own a local per-message commit. This makes partial batches truthful: an
earlier commit stays successful if a later message or final batch commit fails.
Duplicate creates and missing mirrors produce no mutation success. These changes
do not make RBAC, HBI, Kafka notifications or offset commits atomic.

View events contain identifiers, never names, descriptions or configuration.
API callers supply the complete validated actor context, including service-account
identity. Legacy internal repository callers provide org/principal IDs without
inventing an identity type. Deleting a view locks the parent and deletes preferences with SQL `RETURNING`,
recording only rows removed by that transaction under the deleting actor. No-op view changes, repeated
default selections and missing preference deletes produce no mutation event.
`SET_DEFAULT` represents the atomic conditional upsert; its SQL result determines
whether a value changed, including concurrent inserts/updates. It does not claim
a separate CREATE/UPDATE outcome based on an earlier unlocked read.

Staleness uses the organization ID as the stable policy scope. Resetting to
system defaults logs `DELETE` only when it removes a custom row, including the
default-equivalent POST/PATCH early-return paths. Policy rows are locked before
update/delete decisions. Unchanged policies produce no mutation event. Existing staleness API response/timestamp behavior is preserved.

## Host-app projections and export processing

| Operation | Action / resource type / identifier |
|---|---|
| Changed host-app projection | `UPSERT` / `host_app_data` / `application:host_UUID` |
| Export-service accepts an upload | `EXPORT_UPLOAD` / `export` / export request UUID |
| Export-service acknowledges an existing result | `EXPORT_REPLAY` / `export` / export request UUID |
| Export processing fails | `EXPORT` / `export` / export request UUID when validated |

Projection coverage includes Advisor, Vulnerability, Patch, Compliance, Malware and
Remediations. The actor is the known `host-app-data-consumer` with type `SystemActor`.
The application header identifies the projection kind; it is not presented as an
authenticated producer identity. Tenant scope comes from the validated message.
Each changed row carries an immutable context until the common DB batch commits.
Rollback produces failures for the queued operations, and write errors before a
result exists abort the batch rather than committing partial work.

Conditional SQL upserts return only changed row IDs for auditing. Successfully
processed IDs remain separate for existing completion metrics, including exact
replays. An identical payload/timestamp produces no mutation event; a new report
timestamp is a persisted update. FK fallback skips record `host_not_found`; invalid
per-host data records `invalid_host_data` or `host_data_validation_failed`. Invalid
envelopes/headers use null resource IDs and untrusted tenant scope remains null.
Only static failure reasons are added; projection values and validation details
are excluded from audit output.

An export success means that export-service accepted the upload request. It does
not establish final downloadable-file readiness. A legacy duplicate acknowledgement
uses `EXPORT_REPLAY` with `already_processed`, rather than claiming a new upload.
An accepted error-notification request never becomes an export success. Query,
streaming, serialization, header/credential setup, transport and response failures
produce one safe result, and the HTTP session closes on all processing exits.
Later DB/Kafka-offset processing errors do not relabel an already accepted upload.

Export attribution uses the validated requesting user/service identity and the
export request UUID for correlation. Identifiable HBI schema rejections also emit
failure: valid credentials establish actor/tenant; invalid credentials emit an
actorless `AUTHENTICATE` event. Other applications/sources are not labeled as HBI
exports. Denial records remain single events with `permission_denied`.

`with_message_audit_trace` uses the configured OTel propagator and retains the original producer trace ID when no local
message span exists, including disabled MQ tracing, and clears unrelated ambient
batch traces when the producer context is missing/invalid. Export field values,
files, filters, OAuth/PSK credentials and raw error text are not recorded. Per-host
protected-read applicability is tracked in [Phase 1 (RHINENG-33798)](https://issues.redhat.com/browse/RHINENG-33798);
downstream readiness and delivery evidence are tracked in
[Phase 3 (RHINENG-33800)](https://issues.redhat.com/browse/RHINENG-33800).

## Event fields

| Field | Meaning |
|---|---|
| `timestamp` | UTC emission time in ISO 8601 format. |
| `logger`, `level`, `message` | `inventory.audit`, `INFO`, and `Security audit event`. |
| `action`, `resource_type`, `resource_id` | Static operation name, resource kind and affected identifier; unknown identifiers are null. |
| `outcome` | `success` or `failure`, reflecting the actual result. |
| `principal`, `principal_type`, `org_id` | Validated actor and tenant, or an explicitly supplied system actor and tenant scope. Unknown values remain null. |
| `request_id` | HTTP `x-rh-insights-request-id` or explicit message correlation; no thread-local fallback. |
| `trace_id`, `span_id` | Active OTel context or validated producer trace; independent of sampling. `span_id` is null without a local span. |
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
