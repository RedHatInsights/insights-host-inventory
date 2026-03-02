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

## 11. Production Impact — Validated (5.4M hosts, db.m7g.8xlarge)

### Infrastructure (measured)

All production queries were run against the **read-only replica** (also `db.m7g.8xlarge`).
Index scan counts and cache hit ratio reflect replica read traffic. The primary instance
handles the same read workload plus writes (MQ ingestion), so its cache pressure is
likely equal or worse.

| Parameter | Value |
|-----------|-------|
| Total hosts | **5,365,277** across **135,686 orgs** |
| Database | AWS RDS `db.m7g.8xlarge` (32 vCPUs, 128 GB RAM) |
| Measured on | Read-only replica (same instance type) |
| Table partitioning | `HASH(org_id)`, **32 partitions** (p0–p31) |
| Hosts table total size | **~260 GB** across all partitions (25 GB data + ~235 GB indexes) |
| Index-to-data ratio | **~10:1** — 16 indexes per partition × 32 partitions = 512 index instances |
| `hosts_old` (legacy table) | **361 GB** with 0 rows — dead weight |
| Buffer cache hit ratio | **87.55%** (target: 99%+) — working set exceeds shared_buffers |

### Partition distribution (measured)

32 hash partitions with moderate skew — largest is 2.8× smallest:

| Partition | Size | Partition | Size |
|-----------|------|-----------|------|
| hosts_p28 | **16 GB** (largest) | hosts_p16 | 12 GB |
| hosts_p0 | 11 GB | hosts_p20 | 11 GB |
| hosts_p7 | 11 GB | hosts_p25 | 10 GB |
| hosts_p2 | 9.8 GB | hosts_p19 | 9.5 GB |
| hosts_p14 | 9.4 GB | hosts_p3 | 8.9 GB |
| hosts_p27 | **5.8 GB** (smallest) | hosts_p13 | 5.9 GB |

Partition p28 hosts the largest org (466K hosts), explaining its disproportionate size.

### Index usage audit (measured)

**Essential indexes (billions of scans):**

| Index type | Example | Scans | Verdict |
|------------|---------|-------|---------|
| Primary key (`_pkey`) | hosts_p28_pkey | 26.5B | Essential |
| `org_id_id_insights_id_idx` | hosts_p28 | 6.1B | Essential for dedup |
| `system_profiles_static_host_id_idx` | sp_static_p28 | 6.0B | Essential for JOIN |
| `system_profiles_dynamic_pkey` | sp_dynamic_p2 | 2.3B | Essential |

**Unused or near-unused indexes (candidates for dropping):**

| Index family | Partitions | Total scans | Total size | Action |
|-------------|------------|-------------|------------|--------|
| `hosts_old` (all indexes) | 1 table | **0** | **~319 GB** | Drop entire table |
| `groups_idx` (GIN) | ×32 | **0** | **~1 GB** | Drop — never used for reads |
| `hosts_groups_p*_pkey` | ×32 | **0** | **~860 MB** | Investigate — groups table PKs unused |
| `org_id_idx` | ×32 | 5-7 | ~512 KB | Drop — redundant with composite idx |
| `idx_gin_per_reporter_staleness` | ×32 | **9,754 total** | **14.5 GB** | Evaluate — low vs billions on essential idx |
| `workloads_gin` | ×32 | 4 each | ~250 MB | Drop — negligible usage |
| `subscription_manager_id_idx` | ×32 | 43 each | **~560 MB** | Drop — very low usage |
| `idx_hosts_host_type_id` | ×32 | 86–211 | **~580 MB** | Investigate — low but non-zero |
| **Total reclaimable** | | | **~378 GB+** | |

The remaining indexes (`canonical_facts_gin`, `ansible`, `bootc_status`, `mssql`,
`sap_system`, `operating_system_multi`, `org_id_modified_on_expr_idx`) have >211 scans
each and were not in the bottom 80 — these likely serve active query paths and should
be kept unless further analysis shows otherwise.

### Org size distribution (measured)

| Bucket | Orgs | Total hosts | Largest org |
|--------|------|-------------|-------------|
| ≤100 hosts | 130,096 (96%) | 735K | 100 |
| 101–1K | 4,759 | 1.4M | 1,000 |
| 1K–10K | 762 | 1.9M | 9,987 |
| 10K–50K | 60 | 1.0M | 43,766 |
| 50K–100K | 6 | 409K | 88,822 |
| **>100K** | **3** | **800K** | **466,762** |

### Query validation results (EXPLAIN ANALYZE on production)

| Query | Org | Hosts | Estimate | **Actual** | Notes |
|-------|-----|-------|----------|------------|-------|
| COUNT(DISTINCT) | 12971302 | 23K | 25-50ms | **83ms** | Cold cache (7% hit ratio), bitmap scan |
| COUNT(DISTINCT) | 6819021 | 466K | 150-350ms | **416ms** | Warm cache (100% hits), **seq scan**, CPU-bound |
| Data SELECT page 1 | 6819021 | 466K | 2-10ms | **0.1ms** | Index scan backward, 56 buffer hits |
| Data SELECT OFFSET 5000 | 6819021 | 466K | — | **6ms** | Still fast at deep pagination |
| SAP aggregation | 6819021 | 466K | 400ms-1s | **105ms** | Parallel query (2 workers); only 16K dynamic rows |
| Staleness lookup | 6819021 | 466K | <1ms | **0.02ms** | Index scan, trivial — but runs on every request |

### Key production findings

**1. COUNT(DISTINCT) is confirmed as the #1 bottleneck.**
At 466K hosts, it takes **416ms per request** — a sequential scan even with 100% cache
hits. This is pure CPU work: scanning 650K rows, filtering 466K matches, sorting for
DISTINCT. Every time the largest customer opens the host list, they wait 416ms for just
this one query.

**2. The 87.55% cache hit ratio reveals memory pressure.**
With 260 GB of hosts table + indexes competing for ~32 GB shared_buffers, only frequently
accessed partitions stay hot. Cold orgs (23K hosts on partition p28) had a **7% buffer
cache hit ratio** — meaning 93% of their reads went to disk. This makes medium-sized
orgs proportionally slower than expected.

**3. The 10:1 index-to-data ratio is excessive.**
Each partition has 16 indexes, but only the primary key and `org_id_id_insights_id_idx`
appear in the top 30 most-used indexes. Many indexes (ansible, bootc_status, mssql,
sap_system, canonical_facts GIN, groups GIN) may be rarely used but are maintained on
every write and consume ~235 GB of memory/disk. Dropping unused indexes would:
- Improve cache hit ratio (more room for useful data)
- Speed up INSERTs/UPDATEs in MQ ingestion
- Reduce VACUUM overhead

**4. `hosts_old` is 361 GB of dead weight.**
This legacy unpartitioned table has 0 rows but still occupies 361 GB (42 GB data + 319 GB
indexes). Dropping it would reclaim significant disk space and reduce catalog pressure.

**5. SAP aggregation was better than expected.**
PostgreSQL's parallel query (2 workers) and the fact that `system_profiles_dynamic` has
far fewer rows than hosts (16K vs 466K) kept this at 105ms. Still, the endpoint runs
this query twice (results + count), so the real cost is ~210ms.

**6. Paginated data SELECT is not a problem.**
Even for the 466K org, page 1 is **0.1ms** and deep pagination (OFFSET 5000) is **6ms**.
The `hosts_p0_org_id_modified_on_expr_idx` index handles this perfectly.

### Updated production risk summary

| Priority | Issue | Measured impact | Affected | Action |
|----------|-------|----------------|----------|--------|
| **P1** | COUNT(DISTINCT) pagination | **416ms** for 466K org, **83ms** for 23K org | 9 orgs (50K+), felt by 69 orgs (10K+) | Optimize or eliminate |
| **P2** | ~378 GB of unused/low-use indexes + dead table | 87.5% cache hit ratio, 93% disk reads for cold orgs | All orgs | Drop unused indexes and `hosts_old` |
| **P3** | Staleness query per request | 0.02ms × thousands req/sec | All orgs | Cache in Redis |
| **P4** | SAP aggregation double query | ~210ms for 466K org (2 × 105ms) | 9 orgs (50K+) | Eliminate count query |
| Low | Paginated SELECT | 0.1ms–6ms | None | No action needed |

---

## 12. Next Steps

### Immediate actions — database cleanup (est. ~335 GB reclaimed)

1. **Drop `hosts_old` table** — 361 GB (42 GB data + 319 GB indexes), 0 rows, 0 scans
   on all indexes. Pure dead weight from the partition migration.
2. **Drop `groups_idx`** on all 32 host partitions — ~1 GB, 0 scans. GIN index on
   groups JSONB column that is never used for index-based lookups.
3. **Evaluate `idx_gin_per_reporter_staleness`** on all 32 partitions — **14.5 GB**,
   ~9,754 total scans. Largest reclaimable index on active partitions. Usage is low
   (~10K scans vs billions on essential indexes) but non-zero and uneven across
   partitions (p9: 2,938 scans, p30: 2 scans). Verify which query path uses it
   before dropping — if the `per_reporter_staleness` JSONB filter is rarely used
   by API clients, this is safe to drop.
4. **Drop `workloads_gin`** on all 32 partitions — ~250 MB, only 4 scans each.
5. **Drop `org_id_idx`** on all 32 partitions — ~512 KB, 5-7 scans. Redundant with
   the composite `org_id_id_insights_id_idx` (6.1B scans).
6. **Evaluate `subscription_manager_id_idx`** — ~560 MB, 43 scans. Very low but non-zero;
   verify no API endpoint depends on it before dropping.
7. **Evaluate `idx_hosts_host_type_id`** — ~580 MB, 86-211 scans. Low usage; check if
   the host_type filter endpoint uses this index.

Dropping items 1-5 alone would reclaim **~375 GB** and could improve the buffer cache
hit ratio from 87.5% toward the 99%+ target, dramatically reducing disk I/O for cold orgs.

### Query-level optimizations

8. **Optimize COUNT(DISTINCT) for pagination** — the #1 validated bottleneck (416ms for
   largest org). Evaluate: conditional counting (`count=true` query param), estimated
   counts (`pg_class.reltuples`), or materialized `is_visible` column.
9. **Cache staleness config** — per org_id with short TTL in Redis (Finding 3)
10. **Eliminate double-query on SAP aggregation** — derive count from result set (Finding 8)
11. **Investigate the COUNT query in MQ ingestion** — likely unnecessary (Finding 6)

### New indexes to evaluate

See **Section 13** below for detailed analysis of potential new indexes and their
expected impact.

### Further investigation

12. **Add serialization spans** — custom OTel spans around `serialize_host()` to quantify
    the app logic bottleneck at small org scale (Finding 1)
13. **Profile host UPDATE path** — re-ingesting existing hosts (update vs create) may
    have different query patterns

### Production OTel deployment

14. **Define sampling strategy** — 100% in dev/staging, configurable % in production
15. **Clowder configuration** — document OTLP endpoint and env vars for ClowdApp deployment
16. **Developer workflow guide** — step-by-step for investigating slow requests in Grafana/Tempo

---

## 13. Index Optimization Analysis

### Current index landscape

Each of the 32 host partitions has 16 indexes. The essential indexes (PK, `org_id_id_insights_id_idx`,
`system_profiles_*_host_id_idx`) have billions of scans. The rest range from 0 to a few hundred scans.

**Current indexes per partition** (from migration `28280de3f1ce` and later):

| # | Index | Type | Scans | Status |
|---|-------|------|-------|--------|
| 1 | `hosts_p*_pkey` (id, org_id) | btree | 26.5B | Essential |
| 2 | `hosts_p*_org_id_id_insights_id_idx` | btree UNIQUE | 6.1B | Essential (dedup + replica identity) |
| 3 | `idx_hosts_modified_on_id` (modified_on DESC, id DESC) | btree | High | Essential (pagination ORDER BY) |
| 4 | `idx_hosts_insights_id` | btree | High | Essential (host lookup) |
| 5 | `idx_hosts_host_type_modified_on_org_id` (org_id, modified_on, host_type) | btree | Moderate | Used for filtered pagination |
| 6 | `idx_hosts_last_check_in_id` (last_check_in, id) | btree | Moderate | Used for staleness filter |
| 7 | `idx_hosts_canonical_facts_gin` | GIN | Moderate | Used for canonical facts matching |
| 8 | `idx_hosts_operating_system_multi` | btree (partial) | Moderate | OS aggregation queries |
| 9 | `idx_hosts_host_type_id` (host_type, id) | btree | 86-211 | Low — evaluate |
| 10 | `idx_hosts_subscription_manager_id` | btree | 43 | Low — evaluate |
| 11 | `idx_gin_per_reporter_staleness` | GIN | ~10K total | Low for 14.5 GB — evaluate |
| 12 | `idx_hosts_groups_gin` (groups JSONB) | GIN | **0** | Drop |
| 13 | `idx_hosts_system_profiles_workloads_gin` | GIN | 4 | Drop |
| 14 | `idx_hosts_ansible` (system_profile_facts->'ansible') | btree | Unknown | Legacy — evaluate |
| 15 | `idx_hosts_mssql` (system_profile_facts->'mssql') | btree | Unknown | Legacy — evaluate |
| 16 | `idx_hosts_sap_system` (system_profile_facts->'sap_system') | btree | Unknown | Legacy — evaluate |

### Proposed new indexes

#### Index 1: Covering index for COUNT pagination (HIGH IMPACT)

**Problem**: The `COUNT(DISTINCT id)` query runs on every `GET /hosts` request and does a
sequential scan of all hosts in an org. At 466K hosts it takes 416ms. The query is:
```sql
SELECT count(DISTINCT hosts.id) FROM hosts
WHERE hosts.org_id = $1 AND (now() < stale_timestamp
   OR (now() >= stale_timestamp AND now() < stale_warning_timestamp)
   OR (now() >= stale_warning_timestamp AND now() < deletion_timestamp))
```

The staleness filter uses `stale_timestamp`, `stale_warning_timestamp`, and
`deletion_timestamp` with OR conditions. The OR prevents the planner from using
a single btree range scan.

**Proposed index**:
```sql
CREATE INDEX CONCURRENTLY idx_hosts_org_id_staleness
ON hbi.hosts (org_id, deletion_timestamp)
WHERE deletion_timestamp > now();
```

**Rationale**: The staleness OR conditions effectively reduce to "not culled"
(`deletion_timestamp > now()`) for the common `not_culled` staleness filter, which is
the default. A partial index with this WHERE clause would be:
- Much smaller than a full index (excludes culled hosts)
- Allow an index-only count instead of a sequential scan
- Turn the 416ms seq scan into a ~5-10ms index scan

**Caveat**: This only helps the `not_culled` case. The individual staleness states
(`fresh`, `stale`, `stale_warning`) use different column comparisons. However,
`not_culled` is the default and most common filter. Additionally, `deletion_timestamp`
changes over time, so the partial index `WHERE deletion_timestamp > now()` cannot be
used directly — PostgreSQL requires the WHERE clause to match the query exactly.

**Alternative approach — computed `is_culled` column**:
```sql
ALTER TABLE hbi.hosts ADD COLUMN is_culled boolean
  GENERATED ALWAYS AS (deletion_timestamp <= now()) STORED;
CREATE INDEX CONCURRENTLY idx_hosts_org_id_not_culled
ON hbi.hosts (org_id) WHERE is_culled = false;
```
This requires application support but would give the planner a clean, indexable predicate.
However, PostgreSQL does not support `now()` in generated columns (it's not immutable).
A trigger-based approach would be needed, but staleness timestamps change with each
check-in, making this complex.

**Most practical approach — optimize the query, not the index**:
Since the OR-based staleness filter is fundamentally index-unfriendly, the most impactful
change is to **avoid the COUNT query entirely** for large orgs:
1. **Optional count** — add `?count=true` query parameter; omit count by default
2. **Estimated count** — use `pg_class.reltuples` for large orgs (fast, ~95% accurate)
3. **Count cache** — cache the count per org_id in Redis with a short TTL (30-60s)

**Estimated impact**: Eliminating the COUNT query saves **416ms for the largest org**
and **83ms for medium orgs** on every single list request.

#### Index 2: Composite index for staleness + last_check_in (MEDIUM IMPACT)

**Problem**: The `stale_timestamp_filter` in the default staleness path uses
`Host.last_check_in <= now()` combined with staleness states. The existing
`idx_hosts_last_check_in_id` covers `(last_check_in, id)` but doesn't include `org_id`.

**Proposed index**:
```sql
CREATE INDEX CONCURRENTLY idx_hosts_org_id_last_check_in
ON hbi.hosts (org_id, last_check_in DESC);
```

**Rationale**: This composite index would let PostgreSQL use a single index scan for
the common query pattern: `WHERE org_id = $1 AND last_check_in <= now()`. Currently
the planner may combine two separate indexes (org_id from the dedup index + last_check_in)
via a bitmap scan, which is less efficient.

**Estimated impact**: Could reduce the base filter time by 2-3× for medium-to-large
orgs, benefiting every query that uses staleness filters (which is all of them).

**Estimated size**: ~20 MB per partition × 32 = ~640 MB. Worth the trade-off given
the query frequency.

#### Index 3: SAP workloads on system_profiles_dynamic (LOW-MEDIUM IMPACT)

**Problem**: SAP system aggregation joins `hosts` with `system_profiles_dynamic` and
filters on `workloads->'SAP'->'sap_system'`. The existing `workloads_gin` index on
`hosts.system_profile_facts` is on the wrong table (legacy column) and has only 4 scans.

**Proposed index** (on `system_profiles_dynamic`):
```sql
CREATE INDEX CONCURRENTLY idx_sp_dynamic_sap_system
ON hbi.system_profiles_dynamic ((workloads -> 'SAP' -> 'sap_system'))
WHERE workloads -> 'SAP' -> 'sap_system' IS NOT NULL;
```

**Rationale**: This partial expression index targets exactly the SAP aggregation query
path. Only rows with SAP data are indexed, keeping it small. The query already showed
105ms in production with parallel workers, so this is lower priority than the COUNT fix.

**Estimated impact**: Could reduce SAP aggregation from 105ms to ~20-30ms for large
orgs. The double-query elimination (derive count from results) would have more impact.

**Estimated size**: Small — only SAP systems are indexed. ~5 MB per partition.

### Indexes NOT recommended

| Index idea | Why not |
|------------|---------|
| `(org_id, stale_timestamp, stale_warning_timestamp, deletion_timestamp)` | OR conditions across 3 columns prevent btree range scans. The planner cannot use a single index scan when the filter is `a < X OR (a >= X AND b < Y) OR (b >= Y AND c < Z)` |
| Covering index for pagination `(org_id, modified_on DESC, id DESC) INCLUDE (...)` | Already well-served by `idx_hosts_host_type_modified_on_org_id`. Paginated SELECT is 0.1ms — not a bottleneck |
| GIN on `per_reporter_staleness` (keep existing) | 14.5 GB for ~10K scans. The `registered_with` filter uses complex JSONB operations (`jsonb_typeof`, `has_key`, nested casts) that GIN cannot efficiently serve. The queries fall back to sequential scans anyway |
| Index on `display_name` | Uses `ILIKE '%pattern%'` which cannot use btree indexes. Would need `pg_trgm` GIN for prefix/infix searches, but these queries are infrequent |
| Index on `tags` | Already uses `Host.tags.contains()` with GIN-friendly `@>` operator, served by existing JSONB storage |

### Summary: index changes ranked by impact

| Priority | Action | Space impact | Query impact |
|----------|--------|-------------|--------------|
| **P0** | Avoid COUNT query (app change, not index) | None | -416ms for largest org |
| **P1** | Drop `hosts_old` table | **-361 GB** | Improves cache hit ratio |
| **P2** | Drop zero-scan indexes (groups_gin, workloads_gin, org_id_idx) | **-1.3 GB** | Faster writes, better cache |
| **P3** | Evaluate dropping `per_reporter_staleness` GIN | **-14.5 GB** | Better cache, faster writes |
| **P4** | Add `(org_id, last_check_in DESC)` | +640 MB | Faster staleness filtering |
| **P5** | Drop low-usage indexes (subscription_manager_id, host_type_id) | **-1.1 GB** | Marginal cache improvement |
| **P6** | Add SAP partial index on system_profiles_dynamic | +160 MB | -75ms on SAP aggregation |

The key insight: **dropping unused indexes has higher impact than creating new ones**.
The 87.5% cache hit ratio means the database is memory-starved. Freeing ~378 GB of
unused index space means PostgreSQL can keep more useful data in buffer cache, which
improves ALL queries for ALL orgs — a much broader impact than any single new index.
