# /hbi-event-check - Kafka Event Contract Validator

Validate that Kafka event messages produced by HBI code match the event schema specifications. Detects field drift, type mismatches, missing fields, and header inconsistencies that would break downstream consumers.

## Instructions

### Phase 1: Load Sources

Read all relevant specification and code files.

#### 1.1 Event Specifications

1. Read `swagger/host_events.spec.yaml` — extract all schemas:
   - `HostCreateUpdateEvent` — top-level create/update event envelope
   - `HostDeleteEvent` — top-level delete event envelope
   - `Host` — full host representation (properties, required fields, types)
   - `HostTag`, `HostFacts`, `HostGroup`, `PerReporterStaleness` — nested schemas
   - `HostEventMetadata` — event metadata schema
   - `PlatformMetadata` — platform metadata schema
   - `KafkaMessageHeaders` — Kafka header fields and types
   - `KafkaMessage` — overall message structure (key, value, headers)

2. Read `swagger/host_app_events.spec.yaml` — extract all schemas:
   - `HostAppEvent` — top-level host app event envelope
   - `HostAppItem` — per-host data wrapper
   - Application-specific data schemas: `AdvisorData`, `VulnerabilityData`, `PatchData`, `RemediationsData`, `ComplianceData`, `MalwareData`, `ImageBuilderData`
   - `HostAppMessageHeaders` — Kafka header fields (application enum, request_id)

3. Read `swagger/system_profile.spec.yaml` — note the top-level `SystemProfile` property names (do NOT deep-compare every nested field — the system profile has hundreds of fields and is validated separately by `/hbi-spec-sync`). Just verify that `system_profile` is present as an object type in both spec and code.

#### 1.2 Producer Code

4. Read `app/queue/events.py` — extract:
   - How `HostCreateUpdateEvent` messages are constructed (which fields, in what structure)
   - How `HostDeleteEvent` messages are constructed
   - How Kafka headers are built (the header dict construction)
   - What values are used for `event_type` (created, updated, delete)

5. Read `app/serialization.py` — extract:
   - `DEFAULT_FIELDS` tuple — the base fields serialized for every host
   - `CANONICAL_FACTS_FIELDS` tuple — canonical fact field names
   - `ADDITIONAL_HOST_MQ_FIELDS` tuple — extra fields added when `for_mq=True` (tags, system_profile)
   - The `serialize_host()` function — understand how fields are assembled
   - Any special serialization logic: UUID-to-string conversion, datetime formatting, `host_type` backward compatibility, `per_reporter_staleness` structure, `groups` serialization

6. Read `app/queue/event_producer.py` — extract:
   - The `write_event()` method — how messages are sent to Kafka
   - Topic selection logic
   - Key selection (host ID as message key)

7. Read `app/queue/notifications.py` — extract:
   - All notification types and their schemas (validation-error, system-deleted, system-became-stale, new-system-registered)
   - Base schema structure (org_id, application, bundle, context, events, event_type, timestamp)
   - How notification headers are built

#### 1.3 Consumer Code

8. Read `app/queue/host_app.py` — extract:
   - How incoming host-app messages are parsed
   - Which fields are read from each application's data payload
   - How the `application` header is used to route processing
   - Which application types are handled

#### 1.4 Configuration

9. Read `app/config.py` — extract:
   - All Kafka topic configurations (event_topic, notification_topic, host_app_data_topic, etc.)
   - Default topic names

Present the event topology:

| Direction | Topic | Spec File | Code File(s) |
|-----------|-------|-----------|-------------|
| Produces | platform.inventory.events | host_events.spec.yaml | app/queue/events.py, app/serialization.py |
| Produces | platform.notifications.ingress | *(external contract)* | app/queue/notifications.py |
| Consumes | platform.inventory.host-apps | host_app_events.spec.yaml | app/queue/host_app.py |

### Phase 2: Host Event Contract — Field Comparison

Compare what the spec defines against what the code actually produces.

#### 2.1 Create/Update Event — Host Fields

Extract two lists:

**From spec:** All property names under the `Host` schema in `host_events.spec.yaml`. Note which are in the `required` array.

**From code:** The union of fields produced by `serialize_host(for_mq=True)`:
- `DEFAULT_FIELDS` (id, account, org_id, display_name, ansible_host, facts, reporter, per_reporter_staleness, stale_timestamp, stale_warning_timestamp, culled_timestamp, created, updated, groups, last_check_in, openshift_cluster_id)
- `CANONICAL_FACTS_FIELDS` (insights_id, subscription_manager_id, satellite_id, bios_uuid, ip_addresses, fqdn, mac_addresses, provider_id, provider_type)
- `ADDITIONAL_HOST_MQ_FIELDS` (tags, system_profile)

Cross-reference every field:

| # | Field | In Spec | In Code | Required (Spec) | Status |
|---|-------|---------|---------|-----------------|--------|
| 1 | id | Yes/No | Yes/No | Yes/No | OK / WARN / FAIL |

**Status rules:**
- Field in both spec and code: **OK**
- Field in spec (required) but NOT in code: **FAIL** — downstream consumers expect it
- Field in spec (optional) but NOT in code: **WARN** — consumers may expect it
- Field in code but NOT in spec: **WARN** — undocumented field, spec should be updated

#### 2.2 Create/Update Event — Envelope

Compare the top-level `HostCreateUpdateEvent` schema properties against the event dict constructed in `app/queue/events.py`:

| Field | Spec | Code | Status |
|-------|------|------|--------|
| type | required, enum: created/updated | ? | OK/FAIL |
| timestamp | required, date-time | ? | OK/FAIL |
| host | required, Host schema | ? | OK/FAIL |
| metadata | required, HostEventMetadata | ? | OK/FAIL |
| platform_metadata | optional, PlatformMetadata | ? | OK/WARN |

#### 2.3 Delete Event — Fields

Compare `HostDeleteEvent` schema properties against the delete event dict in `app/queue/events.py`:

| Field | Spec | Code | Required (Spec) | Status |
|-------|------|------|-----------------|--------|
| type | enum: delete | ? | Yes | OK/FAIL |
| id | UUID | ? | Yes | OK/FAIL |
| timestamp | date-time | ? | Yes | OK/FAIL |
| org_id | string | ? | Yes | OK/FAIL |
| metadata | HostEventMetadata | ? | Yes | OK/FAIL |
| account | string | ? | No | OK/WARN |
| insights_id | UUID | ? | No | OK/WARN |
| request_id | string | ? | No | OK/WARN |
| subscription_manager_id | UUID | ? | No | OK/WARN |
| initiated_by_frontend | boolean | ? | No | OK/WARN |
| platform_metadata | PlatformMetadata | ? | No | OK/WARN |

#### 2.4 Metadata Schemas

Verify `HostEventMetadata` (spec requires `request_id`) matches code construction.
Verify `PlatformMetadata` properties (b64_identity, url, request_id) match code.

Present mismatches only (skip OK results to reduce noise). If all fields match, state: *"All host event fields are in sync between spec and code."*

### Phase 3: Kafka Headers Contract

Compare the `KafkaMessageHeaders` schema in `host_events.spec.yaml` against headers set in `app/queue/events.py`.

#### 3.1 Extract Header Definitions

**From spec:** List all properties of `KafkaMessageHeaders`:
- `event_type` — type and enum values
- `request_id` — type and nullability
- `producer` — type
- `insights_id` — type and nullability
- `os_name` — type and nullability
- `reporter` — type and nullability
- `host_type` — type and nullability
- `is_bootc` — type and enum values ("True", "False")

**From code:** Find the header dict construction in `app/queue/events.py`. Extract every key set in the headers dict and the expression used to compute its value.

#### 3.2 Cross-Reference

| Header | In Spec | Spec Type | In Code | Code Expression | Status |
|--------|---------|-----------|---------|-----------------|--------|
| event_type | Yes | enum: created, updated, delete | ? | ? | OK/WARN |
| request_id | Yes | string, nullable | ? | ? | OK/WARN |
| producer | Yes | string | ? | ? | OK/WARN |
| insights_id | Yes | string, nullable | ? | ? | OK/WARN |
| os_name | Yes | string, nullable | ? | ? | OK/WARN |
| reporter | Yes | string, nullable | ? | ? | OK/WARN |
| host_type | Yes | string, nullable | ? | ? | OK/WARN |
| is_bootc | Yes | enum: "True", "False" | ? | ? | OK/WARN |

**Status rules:**
- Header in spec but not set by code: **WARN**
- Header set by code but not in spec: **WARN** (undocumented)
- Type mismatch (e.g., spec says string enum but code sends boolean): **FAIL**
- Matching: **OK**

#### 3.3 Value Constraint Check

For enum-typed headers:
- `event_type`: Verify code only sends values from the spec's enum list
- `is_bootc`: Verify code sends string `"True"`/`"False"` (not Python `True`/`False`)

For nullable headers:
- Verify code can actually produce `None` for headers marked nullable in the spec

### Phase 4: Host App Events Contract

Compare `swagger/host_app_events.spec.yaml` against consumer code.

#### 4.1 Envelope Structure

Compare `HostAppEvent` schema against what `app/queue/host_app.py` expects:

| Field | Spec | Consumer Reads | Required (Spec) | Status |
|-------|------|---------------|-----------------|--------|
| org_id | string | ? | Yes | OK/FAIL |
| timestamp | date-time | ? | Yes | OK/WARN |
| hosts | array[HostAppItem] | ? | Yes | OK/FAIL |

#### 4.2 Application Data Schemas

For each application defined in the spec, compare the data schema against what the consumer code reads and stores.

**Applications to check:**
1. **Advisor** — spec fields: `recommendations`, `incidents`
2. **Vulnerability** — spec fields: `total_cves`, `critical_cves`, `high_severity_cves`, `cves_with_security_rules`, `cves_with_known_exploits`
3. **Patch** — spec fields: `installable_advisories`, `template`, `rhsm_locked_version`
4. **Remediations** — spec fields: `remediations_plans`
5. **Compliance** — spec fields: `policies`, `last_scan`
6. **Malware** — spec fields: `last_status`, `last_matches`, `last_scan`
7. **ImageBuilder** — spec fields: `image_name`, `image_status`

For each application:
1. Extract fields from the spec's data schema
2. Find the corresponding handler in the consumer code
3. Extract which fields the handler reads, validates, or stores
4. Cross-reference:

| Application | Field | In Spec | Consumed by Code | Status |
|------------|-------|---------|-----------------|--------|
| vulnerability | total_cves | Yes | Yes/No | OK/WARN |
| vulnerability | new_field | No | Yes | WARN |

**Status rules:**
- Spec field consumed by code: **OK**
- Spec field NOT consumed by code: **INFO** (acceptable if optional — consumer may intentionally skip fields)
- Code consumes field NOT in spec: **WARN** (consumer depends on undocumented field)

#### 4.3 Application Header Enum

Compare the `application` enum in `HostAppMessageHeaders` against the application types handled by the consumer:

| Application | In Spec Enum | Handled by Consumer | Status |
|------------|-------------|-------------------|--------|
| advisor | Yes/No | Yes/No | OK/WARN |
| vulnerability | Yes/No | Yes/No | OK/WARN |
| patch | Yes/No | Yes/No | OK/WARN |
| remediations | Yes/No | Yes/No | OK/WARN |
| compliance | Yes/No | Yes/No | OK/WARN |
| malware | Yes/No | Yes/No | OK/WARN |
| image_builder | Yes/No | Yes/No | OK/WARN |

**Status rules:**
- In spec AND handled: **OK**
- In spec but NOT handled: **WARN** — consumer will drop messages for this application
- Handled but NOT in spec: **WARN** — undocumented application type

### Phase 5: Notification Events — Structural Consistency

Since there is no local spec file for the notification topic (`platform.notifications.ingress` follows an external Red Hat Notifications contract), perform a **structural consistency check** across all notification types.

#### 5.1 Base Structure Verification

For each notification type produced by `app/queue/notifications.py`:
- `validation-error`
- `system-deleted`
- `system-became-stale`
- `new-system-registered`

Verify each includes the required base fields:

| Field | Expected | validation-error | system-deleted | system-became-stale | new-system-registered |
|-------|----------|-----------------|----------------|--------------------|-----------------------|
| org_id | string | ? | ? | ? | ? |
| application | "inventory" | ? | ? | ? | ? |
| bundle | "rhel" | ? | ? | ? | ? |
| context | object | ? | ? | ? | ? |
| events | array | ? | ? | ? | ? |
| event_type | string | ? | ? | ? | ? |
| timestamp | datetime | ? | ? | ? | ? |

#### 5.2 Context and Payload Schemas

Note the two distinct schema patterns:
- **Standard notifications** (system-deleted, system-became-stale, new-system-registered): use `BaseContextSchema` (inventory_id, hostname, display_name, rhel_version, tags) + `BasePayloadSchema` (insights_id, subscription_manager_id, satellite_id, groups)
- **Validation-error notifications**: use `HostValidationErrorContextSchema` (event_name, display_name) + `HostValidationErrorPayloadSchema` (request_id, display_name, canonical_facts, error)

Flag any notification type that deviates from its expected schema pattern: **WARN**.

#### 5.3 Notification Headers

Verify all notification types set consistent headers:
- `event_type` — the notification type string
- `request_id` — request context
- `producer` — hostname
- `rh-message-id` — UUID for deduplication

Flag any missing headers: **WARN**.

### Phase 6: Type Safety and Serialization

Cross-check field types between specs and serialization code. Focus on fields where the Python type might not match the expected wire format.

#### 6.1 UUID Serialization

For all fields with `format: uuid` in the specs:
- Verify `app/serialization.py` converts SQLAlchemy `UUID` objects to strings before inclusion in the event dict
- Check: Does the code use `str(uuid_value)` or does it pass raw UUID objects?

Fields to check: `id`, `insights_id`, `subscription_manager_id`, `satellite_id`, `bios_uuid`, `openshift_cluster_id`

#### 6.2 Datetime Serialization

For all fields with `format: date-time` in the specs:
- Verify code serializes as ISO 8601 strings (not raw Python `datetime` objects)
- Check `serialize_host()` for `.isoformat()` calls or equivalent

Fields to check: `created`, `updated`, `last_check_in`, `stale_timestamp`, `stale_warning_timestamp`, `culled_timestamp`, `timestamp`

#### 6.3 Nullable Fields

For fields marked `nullable: true` in the spec:
- Verify code can produce `None` / `null` for these fields
- Check if the code always populates a value even when the spec allows null

#### 6.4 Enum Fields

For fields with `enum` constraints:
- `provider_type`: spec enum [aws, azure, gcp, alibaba, ibm] — verify code only stores/sends these values
- `host_type` in headers: check the backward compatibility mapping (code maps non-"edge" values to empty string)
- `is_bootc` in headers: spec says enum ["True", "False"] — verify code sends string, not bool

#### 6.5 Array vs Null

For array fields (`ip_addresses`, `mac_addresses`, `tags`, `facts`, `groups`):
- Spec says `type: array` with `nullable: true` — verify code sends `[]` (empty list) or `null`, never omits the field entirely

#### 6.6 Known Backward Compatibility Edge Cases

Document these known serialization behaviors (flag as **INFO**, not issues):
- `host_type` in Kafka headers: only `"edge"` is preserved; all other host types are sent as empty string for backward compatibility with downstream consumers
- System profile `workloads` field: backward compatibility mappings exist for SAP, Ansible, InterSystems, MSSQL, CrowdStrike — old field names are maintained alongside new structure
- `per_reporter_staleness`: uses `additionalProperties` pattern — keys are reporter names, values are staleness data objects

Present results:

| Field | Spec Type | Code Serialization | Wire Format | Status |
|-------|-----------|-------------------|-------------|--------|
| id | string (uuid) | str(host.id) | "550e8400-..." | OK |
| created | string (date-time) | .isoformat() | "2024-01-..." | OK |
| host_type (header) | string | "edge" or "" | string | INFO (compat) |

### Phase 7: Summary Report

#### Contract Health Overview

| Contract | Topic | Status | Issues |
|----------|-------|--------|--------|
| Host Events — created/updated body | platform.inventory.events | IN SYNC / DRIFT | N |
| Host Events — delete body | platform.inventory.events | IN SYNC / DRIFT | N |
| Host Events — Kafka headers | platform.inventory.events | IN SYNC / DRIFT | N |
| Host App Events — envelope | platform.inventory.host-apps | IN SYNC / DRIFT | N |
| Host App Events — per-application data | platform.inventory.host-apps | IN SYNC / DRIFT | N |
| Notifications — structural consistency | platform.notifications.ingress | CONSISTENT / INCONSISTENT | N |
| Type Safety — serialization | all | PASS / WARN | N |

#### Overall Status

Determine the overall verdict:
- **IN SYNC** — all event contracts match between specs and code; no FAIL or WARN findings
- **DRIFT DETECTED** — mismatches found that should be addressed before the next release

#### Consolidated Findings

Present ALL findings with WARN or FAIL status in a single table:

| # | Phase | Contract | Field/Header | Direction | Status | Details | Recommendation |
|---|-------|----------|-------------|-----------|--------|---------|----------------|
| 1 | Host Events | created/updated | field_name | spec → code | WARN/FAIL | description | update spec or code |

If all checks passed, state: *"All event contracts are in sync — no findings."*

#### Action Items

If issues were found, list them ordered by severity:

1. **FAIL** — will cause runtime deserialization errors for downstream consumers. Fix immediately.
   - Include file:line references for both the spec definition and the code that needs updating.
2. **WARN** — potential contract drift that should be reviewed. May cause issues if downstream consumers validate strictly.
   - Include file:line references.
3. **INFO** — known backward compatibility behaviors or intentional design choices. No action needed unless the behavior changes.

## Important Notes

- This command is **read-only** — it analyzes specs and code but never modifies them.
- The system profile schema (`swagger/system_profile.spec.yaml`) is NOT deep-compared field by field — it has hundreds of properties and is validated separately by `/hbi-spec-sync`. This command only verifies that `system_profile` is present as an object in both the event spec and the serialization code.
- Notification events (`platform.notifications.ingress`) follow an **external Red Hat Notifications contract** — there is no local spec file. Phase 5 performs a structural consistency check only.
- The `host_type` backward compatibility mapping (only "edge" is preserved in Kafka headers) is **intentional** — do not flag it as an error. Downstream consumers depend on this behavior.
- Fields may appear in the spec as `nullable: true` and `required: false` — a field being absent from the serialized output is different from it being present with a `null` value. Pay attention to this distinction when comparing.
- The `openshift_cluster_id` field may appear in serialization code but not in all versions of the event spec — check the actual spec file, not assumptions.
- For host-app events, the `image_builder` application was recently dropped (migration `5d158622cabd`). If it still appears in the spec but not in the consumer, flag as **INFO** (cleanup needed in spec, not a runtime issue).
