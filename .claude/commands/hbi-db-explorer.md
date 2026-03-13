# /hbi-db-explorer - Interactive Database Explorer for HBI

Explore the HBI PostgreSQL database in the local development environment. Provides dashboard overview, table exploration, partition analysis, index health, staleness inspection, outbox monitoring, and ad-hoc query execution — all read-only via `podman compose -f dev.yml exec -T db psql`.

## Input

The action to perform is provided as: $ARGUMENTS

Supported actions:
- **(empty)** — dashboard overview (table sizes, row counts, DB size, Alembic head)
- **`hosts`** — top 10 orgs by host count
- **`hosts <org_id>`** — list hosts for a specific org (limited to 25)
- **`groups`** — top 10 orgs by group count
- **`groups <org_id>`** — groups for a specific org with member counts
- **`partitions`** — partition analysis with row counts and skew detection
- **`indexes`** — index sizes, usage statistics, unused/missing index detection
- **`staleness`** — staleness configuration overview across all orgs
- **`staleness <org_id>`** — staleness details and host state counts for a specific org
- **`outbox`** — outbox queue inspection (depth, recent events, stuck detection)
- **`query <SQL>`** — execute a read-only SQL query (SELECT only, 10s timeout)

## Instructions

### Phase 1: Verify DB Connectivity

Before any query, verify the database is reachable:

```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c "SELECT 1;"
```

If this fails, report: "Database is not reachable. Is the dev environment running? Try `make hbi-up` or `podman compose -f dev.yml up -d`." and stop.

### Phase 2: Route Action

Parse `$ARGUMENTS` to determine which action to run:

- If empty or blank → **Dashboard**
- If starts with `hosts` → **Hosts** (extract optional second token as org_id)
- If starts with `groups` → **Groups** (extract optional second token as org_id)
- If equals `partitions` → **Partitions**
- If equals `indexes` → **Indexes**
- If starts with `staleness` → **Staleness** (extract optional second token as org_id)
- If equals `outbox` → **Outbox**
- If starts with `query` → **Query** (everything after `query ` is the SQL)
- Otherwise → report unrecognized action and list available actions

---

### Action: Dashboard (default — no arguments)

Run these queries and present a combined dashboard:

**Query 1 — Table sizes and row counts:**
```sql
SELECT
    s.schemaname || '.' || s.relname AS table_name,
    CASE WHEN c.relkind = 'r' THEN 'table'
         WHEN c.relkind = 'p' THEN 'partitioned'
         ELSE c.relkind::text END AS type,
    s.n_live_tup AS estimated_rows,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size,
    pg_size_pretty(pg_relation_size(s.relid)) AS data_size,
    pg_size_pretty(pg_indexes_size(s.relid)) AS index_size
FROM pg_stat_user_tables s
JOIN pg_class c ON s.relid = c.oid
WHERE s.schemaname = 'hbi'
ORDER BY pg_total_relation_size(s.relid) DESC;
```

**Query 2 — Partition counts per partitioned table:**
```sql
SELECT
    parent.relname AS parent_table,
    COUNT(child.relname) AS partition_count
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
JOIN pg_namespace ns ON parent.relnamespace = ns.oid
WHERE ns.nspname = 'hbi'
GROUP BY parent.relname
ORDER BY parent.relname;
```

**Query 3 — Exact counts for non-partitioned tables (small, fast):**
```sql
SELECT 'groups' AS table_name, COUNT(*) AS exact_count FROM hbi.groups
UNION ALL SELECT 'staleness', COUNT(*) FROM hbi.staleness
UNION ALL SELECT 'outbox', COUNT(*) FROM hbi.outbox;
```

**Query 4 — Total database size:**
```sql
SELECT pg_size_pretty(pg_database_size('insights')) AS database_size;
```

**Query 5 — Current Alembic migration head:**
```sql
SELECT version_num FROM hbi.alembic_version;
```

**Output format — present as two sections:**

Summary:
```
| Metric | Value |
|--------|-------|
| Total database size | <size> |
| Alembic migration head | <version_num> |
| Total hosts (estimated) | <N> |
| Total groups | <N> |
| Staleness configs | <N> |
| Outbox queue depth | <N> |
```

Table details:
```
| Table | Type | Est. Rows | Total Size | Data Size | Index Size |
|-------|------|-----------|------------|-----------|------------|
```

**Edge cases:**
- If `pg_stat_user_tables` returns no rows for `hbi` schema → report: "No HBI tables found. Have migrations been run? Try `make hbi-migrate`."
- If `alembic_version` table does not exist → report: "No Alembic version table found. Run `make hbi-migrate` to initialize."

---

### Action: hosts

**Without org_id — top 10 orgs by host count:**
```sql
SELECT
    org_id,
    COUNT(*) AS host_count,
    COUNT(DISTINCT host_type) AS host_types,
    COUNT(DISTINCT reporter) AS reporters,
    MIN(created_on)::date AS earliest_host,
    MAX(modified_on)::date AS latest_update
FROM hbi.hosts
GROUP BY org_id
ORDER BY host_count DESC
LIMIT 10;
```

Present as a table. If no rows, report: "No hosts in the database. Use the API or Kafka MQ to create hosts."

**With org_id — list hosts for that org:**

First, show a summary:
```sql
SELECT
    COUNT(*) AS total_hosts,
    COUNT(DISTINCT host_type) AS distinct_host_types,
    COUNT(DISTINCT reporter) AS distinct_reporters,
    SUM(CASE WHEN stale_timestamp > NOW() THEN 1 ELSE 0 END) AS fresh_hosts,
    SUM(CASE WHEN stale_timestamp <= NOW() AND (deletion_timestamp IS NULL OR deletion_timestamp > NOW()) THEN 1 ELSE 0 END) AS stale_hosts,
    MIN(created_on)::date AS oldest_host,
    MAX(modified_on)::date AS newest_update
FROM hbi.hosts
WHERE org_id = '<org_id>';
```

Then, show the host list (limited to 25):
```sql
SELECT
    id,
    display_name,
    host_type,
    reporter,
    stale_timestamp::date AS stale_date,
    created_on::date AS created,
    modified_on::date AS modified,
    CASE
        WHEN stale_timestamp > NOW() THEN 'fresh'
        WHEN deletion_timestamp IS NOT NULL AND deletion_timestamp < NOW() THEN 'culled'
        WHEN stale_warning_timestamp IS NOT NULL AND stale_warning_timestamp < NOW() THEN 'stale_warning'
        ELSE 'stale'
    END AS state
FROM hbi.hosts
WHERE org_id = '<org_id>'
ORDER BY modified_on DESC
LIMIT 25;
```

**Edge cases:**
- If org_id returns 0 rows → report: "No hosts found for org_id `<org_id>`. Run `/hbi-db-explorer hosts` without arguments to see available orgs."

---

### Action: groups

**Without org_id — top 10 orgs by group count:**
```sql
SELECT
    g.org_id,
    COUNT(*) AS group_count,
    SUM(CASE WHEN g.ungrouped THEN 1 ELSE 0 END) AS ungrouped_groups,
    MIN(g.created_on)::date AS earliest_group,
    MAX(g.modified_on)::date AS latest_update
FROM hbi.groups g
GROUP BY g.org_id
ORDER BY group_count DESC
LIMIT 10;
```

If no rows, report: "No groups found. Groups can be created via the Groups API."

**With org_id — groups with member counts:**
```sql
SELECT
    g.id,
    g.name,
    g.ungrouped,
    g.created_on::date AS created,
    g.modified_on::date AS modified,
    COALESCE(hg.member_count, 0) AS member_count
FROM hbi.groups g
LEFT JOIN (
    SELECT group_id, COUNT(*) AS member_count
    FROM hbi.hosts_groups
    WHERE org_id = '<org_id>'
    GROUP BY group_id
) hg ON g.id = hg.group_id
WHERE g.org_id = '<org_id>'
ORDER BY g.name;
```

**Edge cases:**
- If org_id has no groups → report: "No groups found for org_id `<org_id>`."

---

### Action: partitions

**Query 1 — Partition details with row counts and sizes:**
```sql
SELECT
    parent.relname AS parent_table,
    child.relname AS partition_name,
    COALESCE(pg_stat.n_live_tup, 0) AS estimated_rows,
    pg_size_pretty(pg_total_relation_size('hbi.' || child.relname)) AS total_size,
    pg_size_pretty(pg_relation_size('hbi.' || child.relname)) AS data_size
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
JOIN pg_namespace ns ON parent.relnamespace = ns.oid
LEFT JOIN pg_stat_user_tables pg_stat
    ON pg_stat.relname = child.relname AND pg_stat.schemaname = 'hbi'
WHERE ns.nspname = 'hbi'
ORDER BY parent.relname, child.relname;
```

**Query 2 — Skew analysis (per parent table):**
```sql
WITH partition_stats AS (
    SELECT
        parent.relname AS parent_table,
        child.relname AS partition_name,
        COALESCE(pg_stat.n_live_tup, 0) AS row_count
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    JOIN pg_namespace ns ON parent.relnamespace = ns.oid
    LEFT JOIN pg_stat_user_tables pg_stat
        ON pg_stat.relname = child.relname AND pg_stat.schemaname = 'hbi'
    WHERE ns.nspname = 'hbi'
)
SELECT
    parent_table,
    COUNT(*) AS partition_count,
    SUM(row_count) AS total_rows,
    MIN(row_count) AS min_rows,
    MAX(row_count) AS max_rows,
    ROUND(AVG(row_count)) AS avg_rows,
    CASE
        WHEN AVG(row_count) > 0 THEN
            ROUND((MAX(row_count) - AVG(row_count)) / NULLIF(AVG(row_count), 0) * 100, 1)
        ELSE 0
    END AS max_skew_pct
FROM partition_stats
GROUP BY parent_table
ORDER BY parent_table;
```

Present partition details and the skew summary. Flag any partition with `max_skew_pct > 100` as **SKEWED**.

**Edge cases:**
- If only 1 partition per table → note: "Only 1 partition per table detected. This is the default dev configuration (`HOSTS_TABLE_NUM_PARTITIONS=1`). Production uses multiple partitions for horizontal scaling."
- Note that `n_live_tup` is an estimate; suggest `ANALYZE hbi.<table>;` for more accurate numbers.

---

### Action: indexes

**Query 1 — All indexes with sizes and usage stats:**
```sql
SELECT
    schemaname || '.' || indexrelname AS index_name,
    schemaname || '.' || relname AS table_name,
    pg_size_pretty(pg_relation_size(schemaname || '.' || indexrelname)) AS index_size,
    idx_scan AS scans,
    idx_tup_read AS tuples_read,
    idx_tup_fetch AS tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'hbi'
ORDER BY pg_relation_size(schemaname || '.' || indexrelname) DESC;
```

**Query 2 — Index definitions:**
```sql
SELECT indexname, tablename, indexdef
FROM pg_indexes
WHERE schemaname = 'hbi'
ORDER BY tablename, indexname;
```

Analyze the results and report:
- **Unused indexes**: where `idx_scan = 0` and the index is NOT a primary key or unique constraint
- **Large indexes**: any index larger than 50% of its table's data size
- Note: "Low scan counts are expected in dev environments. These stats are meaningful in production."

---

### Action: staleness

**Without org_id — all staleness configs:**
```sql
SELECT
    s.org_id,
    ROUND(s.conventional_time_to_stale / 86400.0, 1) AS stale_days,
    ROUND(s.conventional_time_to_stale_warning / 86400.0, 1) AS warning_days,
    ROUND(s.conventional_time_to_delete / 86400.0, 1) AS delete_days,
    s.created_on::date AS created,
    s.modified_on::date AS modified,
    COALESCE(h.host_count, 0) AS host_count
FROM hbi.staleness s
LEFT JOIN (
    SELECT org_id, COUNT(*) AS host_count
    FROM hbi.hosts GROUP BY org_id
) h ON s.org_id = h.org_id
ORDER BY host_count DESC;
```

If no staleness configs exist, report: "No custom staleness configurations found. All orgs are using system defaults."

Also show the default values as reference:

| Setting | Default |
|---------|---------|
| Time to stale | 26 hours (93600s) |
| Time to stale warning | 7 days (604800s) |
| Time to delete | 14 days (1209600s) |

(Read the actual constants from `app/culling.py` to confirm these defaults.)

**With org_id — detailed staleness:**

Show the staleness config for this org:
```sql
SELECT id, org_id,
    conventional_time_to_stale,
    conventional_time_to_stale_warning,
    conventional_time_to_delete,
    created_on, modified_on
FROM hbi.staleness WHERE org_id = '<org_id>';
```

Show host state counts:
```sql
SELECT
    CASE
        WHEN stale_timestamp > NOW() THEN 'fresh'
        WHEN deletion_timestamp IS NOT NULL AND deletion_timestamp < NOW() THEN 'culled'
        WHEN stale_warning_timestamp IS NOT NULL AND stale_warning_timestamp < NOW() THEN 'stale_warning'
        ELSE 'stale'
    END AS state,
    COUNT(*) AS count
FROM hbi.hosts
WHERE org_id = '<org_id>'
GROUP BY state
ORDER BY count DESC;
```

Show hosts closest to deletion (top 10):
```sql
SELECT
    id, display_name, reporter,
    stale_timestamp::date AS stale_date,
    deletion_timestamp::date AS deletion_date,
    deletion_timestamp - NOW() AS time_until_deletion
FROM hbi.hosts
WHERE org_id = '<org_id>'
    AND deletion_timestamp IS NOT NULL
    AND deletion_timestamp > NOW()
ORDER BY deletion_timestamp ASC
LIMIT 10;
```

**Edge cases:**
- If the org has no custom config → note: "Org `<org_id>` has no custom staleness configuration. Using system defaults."
- If no hosts are close to deletion → note: "No hosts approaching deletion for this org."

---

### Action: outbox

**Query 1 — Events by operation type:**
```sql
SELECT
    operation,
    aggregatetype,
    COUNT(*) AS event_count
FROM hbi.outbox
GROUP BY operation, aggregatetype
ORDER BY event_count DESC;
```

**Query 2 — Recent events (last 10):**
```sql
SELECT id, aggregatetype, aggregateid, operation, version
FROM hbi.outbox
ORDER BY id DESC
LIMIT 10;
```

**Query 3 — Total outbox size:**
```sql
SELECT
    COUNT(*) AS total_events,
    pg_size_pretty(pg_total_relation_size('hbi.outbox')) AS table_size
FROM hbi.outbox;
```

**Interpretation:**
- If outbox is empty → report: "Outbox is empty. This is the expected state when Debezium is running and consuming events."
- If outbox has many events → suggest: "A large outbox count may indicate Debezium is not running or is misconfigured. Check Kafka/Debezium status with `podman compose -f dev.yml logs kafka`."

---

### Action: query

**Safety checks before execution:**

1. Trim and normalize the SQL string.
2. **Reject non-SELECT statements.** If the SQL (case-insensitive, ignoring leading whitespace) starts with any of: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `VACUUM`, `ANALYZE`, `REINDEX`, `CLUSTER`, `COMMENT`, `LOCK`, `SET`, `RESET`, `BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT` — reject with: "Only SELECT queries are allowed. This command is read-only for safety."
3. **Auto-add LIMIT**: If the query does not contain `LIMIT` (case-insensitive), append `LIMIT 100` to prevent unbounded result sets.
4. **Timeout**: Prepend `SET statement_timeout = '10s';` before the user's query.

**Execution:**
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -c "SET statement_timeout = '10s'; <USER_SQL>"
```

Present the results as a markdown table. Use the default psql table formatting.

**Edge cases:**
- If the query returns 0 rows → report: "Query returned 0 rows."
- If the query fails with a syntax error → show the PostgreSQL error message.
- If the query times out → report: "Query exceeded 10-second timeout. Consider adding more specific WHERE clauses or LIMIT."

---

## Important Notes

- **Read-only**: This command executes only SELECT queries against the local development database. It never modifies data.
- **Development database only**: All queries run against the local Podman-managed PostgreSQL via `podman compose -f dev.yml exec -T db psql -U insights -d insights`. This is not intended for production databases.
- **Estimated row counts**: The dashboard uses `pg_stat_user_tables.n_live_tup` which is an estimate maintained by autovacuum. For exact counts, use `query SELECT COUNT(*) FROM hbi.<table> WHERE org_id = '<org_id>'`.
- **Partitioned tables**: `hosts`, `hosts_groups`, `system_profiles_static`, and `system_profiles_dynamic` are HASH-partitioned by `org_id`. Queries are most efficient when they include `org_id` in the WHERE clause (enables partition pruning).
- **Schema**: All HBI tables live in the `hbi` schema. Use `hbi.<table>` in raw queries.
- **Staleness values**: Staleness durations in the `staleness` table are stored in seconds. This command converts them to days for readability.
- **Single-partition dev setup**: The default dev configuration uses `HOSTS_TABLE_NUM_PARTITIONS=1`, meaning each partitioned table has only one partition. The partition analysis is more meaningful with multiple partitions (as in production).
