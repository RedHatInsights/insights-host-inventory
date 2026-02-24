# OpenTelemetry Profiling Findings — HBI

> **Sprint Spike** — February 2026
>
> Results from local profiling of HBI using OpenTelemetry + Grafana Tempo.
> 100 hosts ingested via Kafka MQ, 10 API endpoints profiled, all traces analyzed.

---

## Table of Contents

1. [Profiling Setup](#1-profiling-setup)
2. [High-Level Results](#2-high-level-results)
3. [Finding 1: App Logic Dominates Latency, Not SQL](#3-finding-1-app-logic-dominates-latency-not-sql)
4. [Finding 2: COUNT(DISTINCT) Pagination Query on Every List Request](#4-finding-2-countdistinct-pagination-query-on-every-list-request)
5. [Finding 3: Staleness Config Queried on Every Request](#5-finding-3-staleness-config-queried-on-every-request)
6. [Finding 4: System Profile jsonb_build_object Query](#6-finding-4-system-profile-jsonb_build_object-query)
7. [Finding 5: Host List Fetches All Columns](#7-finding-5-host-list-fetches-all-columns)
8. [Finding 6: MQ Ingestion Runs 16 SQL Queries Per Host](#8-finding-6-mq-ingestion-runs-16-sql-queries-per-host)
9. [Finding 7: system_profiles_static Wide INSERT](#9-finding-7-system_profiles_static-wide-insert)
10. [Next Steps](#10-next-steps)

---

## 1. Profiling Setup

| Parameter | Value |
|-----------|-------|
| Hosts in database | 100 (ingested via Kafka MQ) |
| Org ID | `321` |
| OTel SDK | `opentelemetry-sdk 1.32+` |
| Trace backend | Grafana Tempo (local) |
| Visualization | Grafana (local) |
| Instrumentation | Flask, SQLAlchemy (with SQLCommenter), Requests, manual MQ spans |
| Environment | Docker Compose (`dev.yml`) |

### Endpoints profiled

| # | Endpoint | Response Time |
|---|----------|--------------|
| 1 | `GET /hosts` (default page, 50 results) | 319ms |
| 2 | `GET /hosts?per_page=50` | 154ms |
| 3 | `GET /hosts?display_name=dhcp` | 42ms |
| 4 | `GET /hosts?order_by=updated&order_how=DESC` | 157ms |
| 5 | `GET /groups` | 40ms |
| 6 | `GET /hosts/{id}/system_profile` | 132ms |
| 7 | `GET /hosts/{id}` | 52ms |
| 8 | `GET /hosts?registered_with=insights` | 193ms |
| 9 | `GET /system_profile/sap_system` | 52ms |
| 10 | `GET /hosts?tags=insights-client/os=linux` | 44ms |

---

## 2. High-Level Results

### API endpoints — time breakdown

| Endpoint | Total | SQL Time | App Logic | SQL % |
|----------|-------|----------|-----------|-------|
| `GET /hosts` (default page) | 221ms | 20ms | **201ms** | 9% |
| `GET /hosts/{id}/system_profile` | 108ms | 28ms | **81ms** | 26% |
| `GET /hosts?per_page=50` | 68ms | 10ms | **58ms** | 14% |
| `GET /hosts?registered_with=insights` | 64ms | 9ms | **55ms** | 14% |

### MQ ingestion — time breakdown

| Operation | Total | SQL Time | App Logic | SQL % |
|-----------|-------|----------|-----------|-------|
| MQ batch (1 host, slowest) | 619ms | 106ms | **513ms** | 17% |
| MQ batch (1 host, typical) | ~140ms | ~50ms | ~90ms | 36% |

### Aggregate SQL patterns across all API traces

| Query Pattern | Max | Avg | Count | Description |
|---------------|-----|-----|-------|-------------|
| `jsonb_build_object` system profile | 23.6ms | 23.6ms | 1 | System profile construction |
| `COUNT(DISTINCT hosts.id)` | 11.5ms | 4.3ms | 7 | Pagination total count |
| Host data SELECT (all columns) | 6.3ms | 4.0ms | 8 | Main host list query |
| Groups SELECT | 6.1ms | 6.1ms | 1 | Group list query |
| `COUNT(*)` subquery | 3.9ms | 3.9ms | 1 | System profile count |
| Staleness SELECT | 2.7ms | 2.7ms | 1 | Staleness config lookup |

---

## 3. Finding 1: App Logic Dominates Latency, Not SQL

### Observation

Across all profiled API endpoints, **Python application logic consistently accounts for
80-90% of total request latency**, with SQL queries contributing only 9-26%.

For the slowest request (`GET /hosts`, 221ms), only 20ms was spent in SQL. The remaining
201ms was spent in Python — serialization, middleware, validation, and response construction.

### Trace evidence

```
GET /hosts (221ms total, 6 spans, 3 SQL queries)
├── SQL: COUNT(DISTINCT hosts.id)     11.5ms
├── SQL: SELECT hosts.*                6.3ms
├── SQL: SELECT staleness.*            2.2ms
└── App logic (serialization, etc.)  201.4ms  ← 91% of total time
```

### Root cause

The host serialization pipeline (converting SQLAlchemy models to JSON response bodies) is
compute-heavy. Each host goes through multiple serialization steps including:
- `serialize_host()` — converts the ORM model to a dict
- Staleness timestamp calculation per host
- System profile field extraction
- Group membership resolution
- Tag processing

### Impact

At production scale with large pages (50-100 hosts), serialization cost grows linearly
with page size. This is likely a significant contributor to p99 latency on host list
endpoints.

### Suggested optimization

- Profile the serialization pipeline with cProfile to identify hotspots
- Consider returning pre-serialized JSONB from PostgreSQL instead of ORM-level serialization
- Evaluate lazy loading for expensive fields (system_profile, tags) when not requested
- Consider adding custom OTel spans around serialization steps to get finer-grained timing

---

## 4. Finding 2: COUNT(DISTINCT) Pagination Query on Every List Request

### Observation

Every paginated host list request executes a separate `COUNT(DISTINCT hosts.id)` query
to compute the total number of results for the `total` field in the response.

This query was observed **7 times** across 11 API traces, with a **max of 11.5ms** and
an average of 4.3ms.

### SQL

```sql
SELECT count(DISTINCT hbi.hosts.id) AS count_1
FROM hbi.hosts
WHERE hbi.hosts.org_id = %(org_id_1)s
  AND (hbi.hosts.stale_timestamp > %(stale_timestamp_1)s
    OR hbi.hosts.stale_timestamp <= %(stale_timestamp_2)s
      AND hbi.hosts.stale_warning_timestamp > %(stale_warning_timestamp_1)s
    OR hbi.hosts.stale_warning_timestamp <= %(stale_warning_timestamp_2)s
      AND hbi.hosts.deletion_timestamp > %(deletion_timestamp_1)s)
```

### Root cause

- Uses `COUNT(DISTINCT id)` instead of `COUNT(*)` — the `DISTINCT` adds overhead
- The staleness filter with multiple OR conditions prevents simple index usage
- This query essentially scans all hosts for the org to get a total count
- Runs on **every** list request, even when the client may not need the total

### Impact

At production scale (orgs with 50K-500K hosts), this count query can become the single
slowest query. It cannot use a covering index efficiently due to the staleness OR conditions.

### Suggested optimization

- **Estimated count**: Use `pg_class.reltuples` for approximate counts on large result sets
- **Conditional count**: Only run the count query if the client requests it (e.g., `count=true` query param)
- **Cached count**: Cache the count per org_id with a short TTL (staleness changes are infrequent)
- **Simplify staleness filter**: Pre-compute an `is_visible` boolean column on the hosts table, updated by the reaper job

---

## 5. Finding 3: Staleness Config Queried on Every Request

### Observation

The staleness configuration table is queried on **every single API request and every MQ
message processed**. This was observed in all 11 API traces and all MQ batch traces.

### SQL

```sql
SELECT hbi.staleness.id, hbi.staleness.org_id,
       hbi.staleness.conventional_time_to_stale,
       hbi.staleness.conventional_time_to_stale_warning,
       hbi.staleness.conventional_time_to_delete,
       hbi.staleness.created_on, hbi.staleness.modified_on
FROM hbi.staleness
WHERE hbi.staleness.org_id = %(org_id_1)s
```

### Root cause

Staleness configuration is per-org but changes extremely rarely (only when an admin updates
staleness settings). Despite this, it's fetched fresh from the database on every request.

### Impact

- Adds ~2-7ms per request
- Adds unnecessary load on the database
- With thousands of requests/second, this is a significant number of redundant queries

### Suggested optimization

- **In-memory cache with TTL**: Cache the staleness config per org_id in Redis or
  in-process with a 5-minute TTL. This eliminates the query for >99% of requests.
- **Note**: HBI already has Redis available via Clowder — this is a natural fit.

---

## 6. Finding 4: System Profile jsonb_build_object Query

### Observation

The `GET /hosts/{id}/system_profile` endpoint executes a query that constructs a massive
JSONB object server-side using `jsonb_strip_nulls(jsonb_build_object(...))` with dozens
of fields from `system_profiles_static` and `system_profiles_dynamic`.

This was the **single slowest SQL query observed: 23.6ms**.

### SQL (truncated)

```sql
SELECT hbi.hosts.id,
  jsonb_strip_nulls(jsonb_build_object(
    'enabled_services', hbi.system_profiles_static.enabled_services,
    'bios_vendor', hbi.system_profiles_static.bios_vendor,
    'host_type', hbi.system_profiles_static.host_type,
    'cpu_model', hbi.system_profiles_static.cpu_model,
    -- ... 50+ more fields from static and dynamic tables
  )) AS system_profile
FROM hbi.hosts
  JOIN hbi.system_profiles_static ...
  JOIN hbi.system_profiles_dynamic ...
WHERE ...
```

### Root cause

- Constructs a very wide JSONB object in PostgreSQL (50+ fields)
- Joins across `hosts`, `system_profiles_static`, and `system_profiles_dynamic`
- `jsonb_strip_nulls` adds processing overhead
- The query is also wrapped in a COUNT subquery for pagination, doubling the cost

### Impact

This is the most expensive single query in the API. At scale, with many hosts per page,
this query will grow significantly.

### Suggested optimization

- **Sparse field selection**: If the API supports `fields` query params, push column
  selection down to the SQL level so only requested fields are included in the `jsonb_build_object`
- **Avoid COUNT on system_profile**: The count subquery re-executes the full `jsonb_build_object` — it should count on simpler columns
- **Materialized view**: If this endpoint is hot, consider a materialized or pre-computed
  system_profile JSONB column

---

## 7. Finding 5: Host List Fetches All Columns

### Observation

The main host list query fetches **all columns** from `hbi.hosts` for every host in the
page. This was observed 8 times with an average of 4.0ms and max of 6.3ms.

### SQL (truncated)

```sql
SELECT hbi.hosts.id, hbi.hosts.account, hbi.hosts.org_id,
       hbi.hosts.insights_id, hbi.hosts.subscription_manager_id,
       hbi.hosts.satellite_id, hbi.hosts.bios_uuid,
       hbi.hosts.ip_addresses, hbi.hosts.fqdn, hbi.hosts.mac_addresses,
       hbi.hosts.provider_id, ...
FROM hbi.hosts
WHERE ...
```

### Root cause

SQLAlchemy's default behavior is to load all mapped columns when querying a model.
The API response may not need all columns (e.g., `ip_addresses`, `mac_addresses`,
`provider_id` are not always displayed).

### Impact

More data transferred from PostgreSQL means larger result sets, more memory usage,
and slower serialization. With wide rows (many canonical facts, JSON fields), this adds up.

### Suggested optimization

- **Column projection**: Use SQLAlchemy's `load_only()` or `defer()` to fetch only the
  columns needed for the API response
- **Depends on API contract**: Need to verify which fields are actually used in the
  response serialization before deferring columns

---

## 8. Finding 6: MQ Ingestion Runs 16 SQL Queries Per Host

### Observation

Processing a single host message through the MQ service generates **16 SQL queries**:
10 SELECTs, 5 INSERTs, 1 DELETE.

### Query breakdown for a single host ingestion

| # | Type | Duration | Purpose |
|---|------|----------|---------|
| 1 | SELECT | 25.2ms | Look up existing host (deduplication) |
| 2 | INSERT | 15.7ms | Insert system_profiles_static |
| 3 | INSERT | 13.7ms | Insert system_profiles_dynamic |
| 4 | SELECT | 13.0ms | COUNT for pagination (why during ingestion?) |
| 5 | INSERT | 7.4ms | Insert host record |
| 6 | SELECT | 6.8ms | Staleness config lookup |
| 7 | SELECT | 5.1ms | Groups lookup |
| 8 | INSERT | 3.6ms | Insert hosts_groups association |
| 9 | INSERT | 3.0ms | Insert outbox event |
| 10 | SELECT | 2.4ms | Re-read host after insert |
| 11-16 | SELECT/DELETE | ~13ms | Additional lookups and cleanup |

### Root cause

The MQ ingestion path does significant work per host:
1. Deduplication check (SELECT existing host by canonical facts)
2. Host upsert (INSERT or UPDATE)
3. System profile split into static and dynamic tables (2 INSERTs)
4. Group membership management
5. Outbox event for downstream consumers
6. Post-processing: serialization, event production, cache update

The **COUNT query (#4)** during MQ ingestion is suspicious — pagination counts should not
be needed when processing a Kafka message.

### Impact

At high ingestion rates (thousands of hosts/minute), 16 queries per host creates
significant database load. The round-trip overhead alone (16 × network latency) adds up.

### Suggested optimization

- **Investigate the COUNT query**: Determine why a pagination count runs during ingestion
  and remove it if unnecessary
- **Batch INSERTs**: When processing multiple hosts in a single `consume()` batch,
  batch the INSERTs into multi-row statements
- **Reduce re-reads**: The host is read again after insert for serialization — consider
  using `RETURNING` clauses to avoid the extra SELECT

---

## 9. Finding 7: system_profiles_static Wide INSERT

### Observation

The INSERT into `hbi.system_profiles_static` is one of the slowest MQ queries at 15.7ms.

### SQL (truncated)

```sql
INSERT INTO hbi.system_profiles_static
  (org_id, host_id, arch, basearch, bios_release_date, bios_vendor,
   bios_version, bootc_status, cloud_provider, cpu_flags, cpu_model, ...)
VALUES (...)
```

### Root cause

This table has a very wide schema (50+ columns) representing the static portion of the
system profile. Every host ingestion inserts a full row with all columns.

### Impact

Wide INSERTs are inherently slower due to the amount of data and potential index updates.
This is structural to the data model.

### Suggested optimization

- **Minimal impact expected**: This is a necessary write for the data model
- **Ensure minimal indexes**: Verify that `system_profiles_static` only has essential
  indexes (org_id, host_id) to minimize index maintenance cost
- **UPSERT optimization**: If the row often already exists, ensure the upsert uses
  `ON CONFLICT ... DO UPDATE` efficiently rather than DELETE + INSERT

---

## 10. Next Steps

### Immediate actions (from spike findings)

1. **Investigate the COUNT query in MQ ingestion** — likely unnecessary, quick win
2. **Cache staleness config** — per org_id with short TTL in Redis, eliminates query from every request
3. **Add serialization spans** — add custom OTel spans around `serialize_host()` to quantify the app logic bottleneck

### Follow-up stories

4. **Optimize COUNT(DISTINCT) for pagination** — evaluate estimated counts or conditional counting
5. **System profile query optimization** — sparse field selection, avoid COUNT on jsonb_build_object
6. **Profile at production scale** — deploy OTel to staging with real data volumes to find scale-dependent bottlenecks

### Production deployment

7. **Define sampling strategy** — 100% in dev/staging, configurable % in production
8. **Clowder configuration** — document OTLP endpoint and env vars for ClowdApp deployment
9. **Developer workflow guide** — step-by-step guide for investigating slow requests in Grafana/Tempo
