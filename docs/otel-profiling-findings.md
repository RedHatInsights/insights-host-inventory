# OpenTelemetry Profiling Findings — HBI

> **Sprint Spike** — February/March 2026
>
> Results from local profiling of HBI using OpenTelemetry + Grafana Tempo.
> Two rounds of profiling: 100 hosts and 10,000 hosts.

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
10. [Finding 8: SAP System Aggregation Query Becomes Dominant at Scale](#10-finding-8-sap-system-aggregation-query-becomes-dominant-at-scale)
11. [Production Impact Estimate (5M hosts, db.m7g.8xlarge)](#11-production-impact-estimate-5m-hosts-dbm7g8xlarge)
12. [Next Steps](#12-next-steps)

---

## 1. Profiling Setup

| Parameter | Value |
|-----------|-------|
| OTel SDK | `opentelemetry-sdk 1.32+` |
| Trace backend | Grafana Tempo (local) |
| Visualization | Grafana (local) |
| Instrumentation | Flask, SQLAlchemy (with SQLCommenter), Requests, manual MQ spans |
| Environment | Docker Compose (`dev.yml`) |
| Org ID | `321` |

### Profiling rounds

| Round | Hosts | Date | Purpose |
|-------|-------|------|---------|
| 1 | 100 | Feb 2026 | Baseline — find structural issues |
| 2 | 10,000 | Mar 2026 | Scale test — find volume-sensitive issues |

### Endpoints profiled (response times)

| # | Endpoint | 100 hosts | 10K hosts | Change |
|---|----------|-----------|-----------|--------|
| 1 | `GET /hosts` (default page) | 319ms | 109ms* | — |
| 2 | `GET /hosts?per_page=50` | 154ms | 162ms | +5% |
| 3 | `GET /hosts?per_page=100` | — | 183ms | (new) |
| 4 | `GET /hosts?display_name=dhcp` | 42ms | 100ms | **+138%** |
| 5 | `GET /hosts?order_by=updated&order_how=DESC` | 157ms | 163ms | +4% |
| 6 | `GET /groups` | 40ms | 33ms | -18% |
| 7 | `GET /hosts/{id}/system_profile` | 132ms | 131ms | 0% |
| 8 | `GET /hosts/{id}` | 52ms | 48ms | -8% |
| 9 | `GET /hosts?registered_with=insights` | 193ms | 138ms | -28% |
| 10 | `GET /system_profile/sap_system` | 52ms | **120ms** | **+131%** |
| 11 | `GET /hosts?tags=...` | 44ms | 72ms | **+64%** |

*\* First request after cold start; warmed-up requests at 10K are in the 50-90ms range.*

---

## 2. High-Level Results

### API endpoints — time breakdown (10K hosts)

| Endpoint | Total | SQL Time | App Logic | SQL % |
|----------|-------|----------|-----------|-------|
| `GET /hosts` (default page) | 168ms | 20ms | **148ms** | 12% |
| `GET /hosts?per_page=50` (warmed) | 91ms | 67ms | **23ms** | 74% |
| `GET /hosts/{id}/system_profile` | 108ms | 27ms | **81ms** | 25% |
| `GET /system_profile/sap_system` | 112ms | **74ms** | 38ms | **66%** |
| `GET /hosts?registered_with=insights` | 56ms | 38ms | 18ms | 67% |

### Key shift from 100 → 10K hosts

At 100 hosts, app logic dominated (80-90% of latency). At 10K hosts, **SQL now accounts
for 35-74% of latency** on most endpoints. The COUNT(DISTINCT) pagination query is the
primary driver, growing from avg 4.3ms to avg **20.5ms** (4.8× increase for 100× more data).

### MQ ingestion — time breakdown (100 hosts)

| Operation | Total | SQL Time | App Logic | SQL % |
|-----------|-------|----------|-----------|-------|
| MQ batch (1 host, slowest) | 619ms | 106ms | **513ms** | 17% |
| MQ batch (1 host, typical) | ~140ms | ~50ms | ~90ms | 36% |

### Aggregate SQL patterns across all API traces (10K hosts)

| Query Pattern | Max | Avg | Count | vs 100 hosts |
|---------------|-----|-----|-------|-------------|
| SAP system aggregation | **42.0ms** | 42.0ms | 1 | (not tested before) |
| `COUNT(DISTINCT hosts.id)` | **33.7ms** | **20.5ms** | 11 | max 3×, avg 4.8× |
| `COUNT(*)` SAP subquery | **32.5ms** | 32.5ms | 1 | (not tested before) |
| Host data SELECT (all columns) | **31.5ms** | 6.5ms | 12 | max 5×, avg 1.6× |
| `jsonb_build_object` system profile | 23.3ms | 23.3ms | 1 | ~same |
| `COUNT(*)` system profile subquery | 3.8ms | 3.8ms | 1 | ~same |
| Groups SELECT | 3.7ms | 3.7ms | 1 | -39% |
| `COUNT(DISTINCT)` with JOIN | 3.5ms | 3.5ms | 1 | (new pattern) |
| Staleness SELECT | 2.3ms | **1.6ms** | 12 | ~same |
| Groups COUNT | 1.5ms | 1.5ms | 1 | ~same |

---

## 3. Finding 1: App Logic Dominates Latency, Not SQL (but SQL catches up at scale)

### Observation

At 100 hosts, **Python application logic accounted for 80-90% of total request latency**,
with SQL contributing only 9-26%.

At 10K hosts, the balance shifts significantly: **SQL now accounts for 35-74% of latency**
on warmed-up requests. The COUNT(DISTINCT) pagination query is the main driver.

### Trace evidence (100 hosts)

```
GET /hosts (221ms total, 6 spans, 3 SQL queries)
├── SQL: COUNT(DISTINCT hosts.id)     11.5ms
├── SQL: SELECT hosts.*                6.3ms
├── SQL: SELECT staleness.*            2.2ms
└── App logic (serialization, etc.)  201.4ms  ← 91% of total time
```

### Trace evidence (10K hosts — warmed up)

```
GET /hosts (91ms total, 3 SQL queries)
├── SQL: COUNT(DISTINCT hosts.id)     33.7ms  ← 3× slower than 100 hosts
├── SQL: SELECT hosts.*               31.5ms  ← 5× slower than 100 hosts
├── SQL: SELECT staleness.*            1.9ms
└── App logic (serialization, etc.)   23.3ms  ← now only 26% of total
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

At 100 hosts, serialization is the bottleneck. At 10K hosts, SQL takes over. At production
scale (50K-500K hosts per org), SQL will dominate — but serialization still matters for
large page sizes (per_page=100).

### Suggested optimization

- **SQL side**: Focus on COUNT(DISTINCT) and host data query optimization (see Findings 2, 5)
- **App side**: Profile the serialization pipeline with cProfile to identify hotspots
- Consider returning pre-serialized JSONB from PostgreSQL instead of ORM-level serialization
- Evaluate lazy loading for expensive fields (system_profile, tags) when not requested
- Consider adding custom OTel spans around serialization steps to get finer-grained timing

---

## 4. Finding 2: COUNT(DISTINCT) Pagination Query on Every List Request

### Observation

Every paginated host list request executes a separate `COUNT(DISTINCT hosts.id)` query
to compute the total number of results for the `total` field in the response.

| Metric | 100 hosts | 10K hosts | Growth |
|--------|-----------|-----------|--------|
| Max | 11.5ms | **33.7ms** | **2.9×** |
| Avg | 4.3ms | **20.5ms** | **4.8×** |
| Count per round | 7 | 11 | — |

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

## 10. Finding 8: SAP System Aggregation Query Becomes Dominant at Scale

### Observation

The `GET /system_profile/sap_system` endpoint was fast at 100 hosts (52ms) but became
the **second slowest endpoint at 10K hosts (120ms, +131%)**. Its SQL now accounts for
**66% of latency** — the highest SQL ratio of any endpoint.

The endpoint executes two queries that together take **74.4ms**.

### SQL

**Query 1 — Aggregation (42.0ms):**
```sql
SELECT anon_1.value AS anon_1_value, count(*) AS count_1
FROM (
  SELECT hbi.system_profiles_dynamic.workloads -> 'SAP' -> 'sap_system' AS value
  FROM hbi.hosts
  JOIN hbi.system_profiles_dynamic ...
  WHERE hbi.hosts.org_id = %(org_id_1)s AND (staleness filters...)
) AS anon_1
GROUP BY anon_1.value
```

**Query 2 — Count of the aggregation (32.5ms):**
```sql
SELECT count(*) AS count_1 FROM (
  SELECT anon_2.value AS anon_2_value, count(*) AS count_2
  FROM (... same subquery as above ...)
  GROUP BY anon_2.value
) AS anon_1
```

### Root cause

- Scans every host in the org and joins with `system_profiles_dynamic` to extract
  a JSONB nested field (`workloads -> 'SAP' -> 'sap_system'`)
- The aggregation cannot use indexes because it operates on a computed JSONB expression
- The COUNT query wraps the full aggregation, effectively running it twice
- Growth is linear with host count — at 100K hosts this would be ~400ms+ per query

### Impact

This endpoint grows linearly with data volume. At production scale, it will be one of
the slowest endpoints. The double execution (aggregation + count of aggregation) doubles
the cost unnecessarily.

### Suggested optimization

- **Eliminate the count query**: The outer COUNT just counts how many distinct SAP system
  values exist — this can be derived from the aggregation result set without a separate query
- **GIN index on JSONB path**: Consider a functional index on
  `(workloads -> 'SAP' -> 'sap_system')` if this query is hot
- **Materialized aggregation**: If SAP system data changes infrequently, cache the
  aggregation result with a TTL

---

## 11. Production Impact Estimate (5M hosts, db.m7g.8xlarge)

### Infrastructure context

| Parameter | Value |
|-----------|-------|
| Total hosts | ~5,000,000 |
| Database | AWS RDS `db.m7g.8xlarge` (32 vCPUs, 128 GB RAM, up to 40K IOPS) |
| Table partitioning | `HASH(org_id)` — all hosts for one org land in the same partition |
| Partition count | Configurable via `HOSTS_TABLE_NUM_PARTITIONS` |
| Estimated table size | ~32 GB for hosts alone, ~100-200 GB including system profiles and indexes |

### Critical insight

Queries filter by `org_id`, so **per-org host count determines query cost**, not total
host count. The hash partitioning by `org_id` means PostgreSQL only scans the partition
containing that org, but all hosts within an org still require a full scan for queries
like COUNT(DISTINCT) with staleness filters.

### Query scaling projections

Production estimates are adjusted ~2-3× faster than local Docker measurements to account
for dedicated CPU, optimized memory management, and NVMe-backed EBS on db.m7g.8xlarge.

#### COUNT(DISTINCT) pagination query — runs on EVERY list request

| Hosts per org | Local estimate | Production estimate | Verdict |
|---------------|----------------|---------------------|---------|
| 1K | ~5ms | **2-3ms** | Fine |
| 10K | ~20ms | **8-15ms** | Acceptable |
| 50K | ~60-100ms | **25-50ms** | Noticeable to users |
| 100K | ~120-200ms | **50-100ms** | **Slow** — users feel this |
| 500K | ~400-700ms | **150-350ms** | **Unacceptable** — breaks SLOs |

The staleness OR conditions prevent efficient index usage, forcing a sequential scan
of all hosts in the org. No amount of hardware fixes an O(n) scan at 500K rows.

#### Host data SELECT (paginated, per_page=50)

| Hosts per org | Production estimate | Verdict |
|---------------|---------------------|---------|
| Any size | **2-10ms** | Bounded by pagination — not volume-sensitive |

However, `ORDER BY modified_on` with large `OFFSET` (deep pagination) degrades as
PostgreSQL must skip rows sequentially.

#### System profile jsonb_build_object (single host lookup)

| Hosts per org | Production estimate | Verdict |
|---------------|---------------------|---------|
| Any size | **10-15ms** | Stable — single-row lookup, cost is JSONB construction |

#### SAP system / workloads aggregation (scans ALL hosts in org)

| Hosts per org | Local estimate | Production estimate | Verdict |
|---------------|----------------|---------------------|---------|
| 1K | ~10ms | **3-5ms** | Fine |
| 10K | ~75ms | **25-40ms** | Acceptable |
| 50K | ~200-350ms | **80-150ms** | **Slow** |
| 100K | ~400-600ms | **150-300ms** | **Unacceptable** |
| 500K | ~1-2s | **400ms-1s** | **Broken** — likely times out |

Scans every host, joins `system_profiles_dynamic`, extracts JSONB, aggregates — and
runs the entire thing **twice** (results + count). This is the #2 concern after pagination.

#### Staleness config SELECT (per request)

| Hosts per org | Production estimate | Verdict |
|---------------|---------------------|---------|
| Any size | **<1ms** per query | Trivial individually, but multiplied by thousands of req/sec = unnecessary DB load |

#### MQ ingestion — 16 queries per host

| Scenario | Production estimate | Verdict |
|----------|---------------------|---------|
| Per host | **15-40ms** total SQL | Acceptable |
| 1K hosts/min ingestion rate | ~15-40 sec DB time/min | Fine |
| 10K hosts/min ingestion rate | ~2.5-7 min DB time/min | **Backpressure risk** — connection pool saturation |

The concern is aggregate DB load during high-ingestion bursts, not individual query speed.

### Production risk summary

| Priority | Issue | Affected orgs | Risk | Finding |
|----------|-------|---------------|------|---------|
| **P1** | COUNT(DISTINCT) pagination | Orgs with >50K hosts | p99 latency SLO breach on every list request | #2 |
| **P2** | SAP/workloads aggregation | Orgs with >50K hosts | Endpoint timeout, double query waste | #8 |
| **P3** | Staleness query on every request | All orgs | Aggregate DB load — thousands of unnecessary queries/sec | #3 |
| **P4** | MQ 16 queries/host | All orgs during ingestion | DB connection pool saturation during bursts | #6 |
| Low | Host data SELECT, system profile | All orgs | Bounded by pagination, not volume-sensitive | #1, #5 |

### Key takeaway

The `db.m7g.8xlarge` is a powerful instance, but **hardware cannot compensate for O(n)
scans on large orgs**. The COUNT(DISTINCT) pagination and SAP aggregation queries are
algorithmic problems — they will be the performance bottleneck for the largest customers
regardless of instance class.

---

## 12. Next Steps

### Immediate actions (quick wins)

1. **Investigate the COUNT query in MQ ingestion** — likely unnecessary, quick win (Finding 6)
2. **Cache staleness config** — per org_id with short TTL in Redis (Finding 3)
3. **Eliminate double-query on SAP aggregation** — derive count from result set (Finding 8)

### High-impact optimizations

4. **Optimize COUNT(DISTINCT) for pagination** — this is the #1 bottleneck at scale,
   growing 4.8× from 100→10K hosts. Evaluate estimated counts, conditional counting,
   or pre-computed `is_visible` column (Finding 2)
5. **System profile query optimization** — avoid wrapping `jsonb_build_object` in COUNT
   subquery; push field selection to SQL (Finding 4)
6. **SAP/workloads JSONB index** — functional GIN index on hot JSONB paths (Finding 8)

### Further investigation

7. **Add serialization spans** — custom OTel spans around `serialize_host()` to quantify
   the remaining app logic bottleneck at small scale (Finding 1)
8. **Profile at production scale** — deploy OTel to staging with real data volumes
   (50K-500K hosts) to validate the scaling trends observed locally
9. **Profile host UPDATE path** — re-ingesting existing hosts (update vs create) may
   have different query patterns

### Production deployment

10. **Define sampling strategy** — 100% in dev/staging, configurable % in production
11. **Clowder configuration** — document OTLP endpoint and env vars for ClowdApp deployment
12. **Developer workflow guide** — step-by-step guide for investigating slow requests in Grafana/Tempo
