# /hbi-query-review - SQLAlchemy Query Performance Analyzer

Analyze all SQLAlchemy queries in the HBI codebase for performance issues: N+1 queries, missing partition pruning, unbounded result sets, index coverage gaps, inefficient bulk operations, and anti-patterns. Acknowledges good patterns already in place.

## Instructions

This command is **read-only** — it analyzes query code but never modifies files or executes queries.

### Phase 1: Load Sources

Read all files that construct, filter, or execute SQLAlchemy queries.

#### 1.1 Query Construction

1. **`api/host_query_db.py`** — extract every function that builds or executes a query:
   - `_find_hosts_entities_query()` — base query builder, outerjoin chain, org_id filter
   - `_find_hosts_model_query()` — model query with `load_only()`
   - `_get_host_list_using_filters()` — conditional eager loading, `defer()`, `func.count()`, pagination
   - `get_host_list()` — main host list entry point
   - `get_host_list_by_id_list()` — ID-based host retrieval
   - `get_host_id_by_insights_id()` — single host lookup
   - `get_tag_list()` — tag aggregation query (note: `.all()` without LIMIT)
   - `get_os_info()` — OS aggregation with GROUP BY (note: `.all()` without LIMIT)
   - `get_sap_system_info()` — SAP system with subquery + paginate
   - `get_sap_sids_info()` — SAP SIDs with `jsonb_array_elements_text` (note: `.all()`)
   - `get_sparse_system_profile()` — dynamic `jsonb_build_object()` construction
   - `get_host_ids_list()` — all host IDs with filters (note: `.all()`)
   - `get_hosts_to_export()` — streaming with `yield_per()` and `joinedload()`
   - `get_all_hosts()` — all host IDs with NO filters beyond org_id (note: `.all()`)
   - `params_to_order_by()` — ORDER BY column mapping

2. **`lib/host_repository.py`** — extract:
   - `host_query(org_id)` — base tenant-isolated query
   - `find_existing_host()` — deduplication with priority-ordered canonical facts
   - `_find_host_by_multiple_facts_in_db_or_in_memory()` — in-memory matching optimization
   - `multiple_canonical_facts_host_query()` — complex OR/AND canonical fact filters
   - `find_existing_host_by_id()` / `find_existing_hosts_by_id_list()` — ID-based lookups
   - `get_host_list_by_id_list_from_db()` — ID list query with RBAC and group joins
   - `get_non_culled_hosts_count_in_group()` — `.count()` with group join
   - `find_non_culled_hosts()` — staleness NOT filter

3. **`lib/group_repository.py`** — extract:
   - `_add_hosts_to_group()` — validation, prior assoc delete, bulk `add_all()`
   - `_remove_hosts_from_group()` — individual `_delete_host_group_assoc()` in a loop
   - `_remove_all_hosts_from_group()` — queries all host IDs then calls `_remove_hosts_from_group()`
   - `_update_hosts_for_group_changes()` — loads all hosts by ID, sets groups in a loop
   - `_produce_host_update_events()` — accesses `host.static_system_profile` in a loop
   - `_invalidate_system_cache()` — accesses `host.static_system_profile` in a loop
   - `serialize_group()` — calls `get_non_culled_hosts_count_in_group()` (N+1 risk when called per group)
   - Validation queries: `validate_add_host_list_to_group()`, `validate_add_host_list_to_group_for_group_create()`

4. **`lib/host_app_repository.py`** — extract:
   - `upsert_host_app_data()` — PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` pattern

5. **`lib/host_delete.py`** — extract:
   - `delete_hosts()` — `while select_query.count()` loop
   - `_delete_host_db_records()` — chunk-based deletion with `limit(chunk_size)`
   - `_delete_host()` — deletes HostGroupAssoc then Host per row

6. **`lib/host_synchronize.py`** — extract:
   - `synchronize_hosts()` — distinct org_ids query, per-org processing
   - `_synchronize_hosts_for_org()` — keyset pagination with `Host.id > last_id`
   - `sync_group_data()` — per-org processing of hosts with empty groups
   - `_sync_group_data_for_org()` — `get_group_using_host_id()` called per host in loop

#### 1.2 Filtering

7. **`api/filtering/db_filters.py`** — extract:
   - `query_filters()` — central filter combiner with dynamic join detection
   - `_is_table_already_joined()` — duplicate join prevention utility
   - `update_query_for_owner_id()` — system identity join with duplicate check
   - `_tags_filter()` — JSONB containment `Host.tags.contains(tag)`
   - `_stale_timestamp_per_reporter_filter()` — complex JSONB path queries with `.astext.cast(DateTime)`
   - `_needs_system_profile_joins()` — dynamic SP join detection based on filter fields
   - `_display_name_filter()` / `_hostname_or_id_filter()` — `ilike('%...%')` patterns

8. **`api/filtering/db_custom_filters.py`** — read to understand system profile filter patterns (JSONB vs column-based)

#### 1.3 Models and Indexes

9. **`app/models/host.py`** — extract:
   - All column definitions, JSONB columns, indexes
   - Relationship definitions: `static_system_profile` (lazy="select"), `dynamic_system_profile` (lazy="select")
   - All `Index()` definitions on the hosts table

10. **`app/models/host_group_assoc.py`** — extract primary key and foreign keys

11. **`app/models/system_profile_static.py`** — extract columns and indexes

12. **`app/models/system_profile_dynamic.py`** — extract columns and indexes

13. **`app/models/group.py`** — extract columns and indexes

#### 1.4 Background Jobs

14. **`jobs/host_reaper.py`** — extract:
    - `filter_hosts_in_state_using_custom_staleness()` — queries ALL staleness objects, builds per-org filters
    - `run()` — main reaper loop with `query.count()` + chunk-based `delete_hosts()`

15. **`app/queue/host_mq.py`** — extract:
    - Batch message processing pattern
    - Session management (commit boundaries)
    - How `find_existing_host()` is called per message

#### 1.5 Configuration

16. **`app/config.py`** — extract:
    - `INVENTORY_DB_POOL_SIZE` (default 5)
    - `INVENTORY_DB_POOL_TIMEOUT` (default 5s)
    - `INVENTORY_DB_STATEMENT_TIMEOUT` (default 30000ms)
    - `INVENTORY_DB_LOCK_TIMEOUT` (default 90000ms)
    - `host_delete_chunk_size`
    - Pool pre-ping setting

Present a configuration summary:

| Setting | Default | Source |
|---------|---------|--------|
| Pool Size | 5 | `INVENTORY_DB_POOL_SIZE` |
| Pool Timeout | 5s | `INVENTORY_DB_POOL_TIMEOUT` |
| Statement Timeout | 30000ms | `INVENTORY_DB_STATEMENT_TIMEOUT` |
| Lock Timeout | 90000ms | `INVENTORY_DB_LOCK_TIMEOUT` |
| Pool Pre-Ping | Enabled | `app/config.py` |
| Delete Chunk Size | (from env) | `host_delete_chunk_size` |

### Phase 2: Query Pattern Inventory

Scan all files from Phase 1 and classify every distinct SQLAlchemy query by its construction pattern.

#### 2.1 Query Classification

For each query found, record:

| # | File:Line | Function | Query Style | Joins | Loading Strategy | Filter Type | Pagination | Result Method | Notes |
|---|-----------|----------|-------------|-------|-----------------|-------------|------------|---------------|-------|
| 1 | `host_query_db.py:NNN` | `_find_hosts_entities_query` | `db.session.query(Host)` | outerjoin(HGA, Group) | — | org_id | — | base query | Conditional SP join |
| 2 | `host_query_db.py:NNN` | `_get_host_list_using_filters` | via base query | (inherited) | `joinedload(SP)`, `defer(SPF)` | dynamic | `.paginate()` | `.items` | Conditional eager loading |
| 3 | `host_query_db.py:NNN` | `get_tag_list` | via base query | (inherited) | — | dynamic | **None (.all())** | `.all()` | **Unbounded** |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Include **every** query-building function — do not omit any.

**Query Style values:** `db.session.query(Model)`, `select(Model)`, `Model.query`, `insert(Model)`, `db.session.execute(text(...))`

**Loading Strategy values:** `joinedload()`, `subqueryload()`, `selectinload()`, `defer()`, `load_only()`, `None` (default lazy)

**Pagination values:** `.paginate()`, `.limit().offset()`, `keyset` (WHERE id > last_id + LIMIT), `yield_per()`, `None` (unbounded)

#### 2.2 Pattern Summary

After the table, report counts:

| Pattern | Count | Files |
|---------|-------|-------|
| Unbounded `.all()` on potentially large tables | N | list |
| Conditional eager loading | N | list |
| Keyset pagination | N | list |
| JSONB containment filter | N | list |
| `func.count()` (optimized) | N | list |
| `.count()` (subquery) | N | list |
| `yield_per()` streaming | N | list |
| `ON CONFLICT DO UPDATE` bulk upsert | N | list |

### Phase 3: N+1 and Lazy Loading Analysis

For every relationship with `lazy="select"` (the default lazy loading strategy), trace ALL code paths where the relationship is accessed.

#### 3.1 Static System Profile Access

The `Host.static_system_profile` relationship uses `lazy="select"` and `uselist=False`.

Search for `.static_system_profile` access across `api/`, `lib/`, `jobs/`, `app/queue/`. For each access:

| # | File:Line | Function | Context | Eager Loading Applied? | In Loop? | Status |
|---|-----------|----------|---------|----------------------|----------|--------|
| 1 | `host_query_db.py:NNN` | `_get_host_list_using_filters` | conditional SP request | Yes (`joinedload`) | No | OK |
| 2 | `host_query_db.py:NNN` | `get_hosts_to_export` | export streaming | Yes (`joinedload`) | Yes (yield_per) | OK |
| 3 | `group_repository.py:NNN` | `_produce_host_update_events` | event header extraction | **No** | **Yes (for loop)** | **FAIL** |
| ... | ... | ... | ... | ... | ... | ... |

#### 3.2 Dynamic System Profile Access

The `Host.dynamic_system_profile` relationship uses `lazy="select"` and `uselist=False`.

Search for `.dynamic_system_profile` access across `api/`, `lib/`, `jobs/`, `app/queue/`. Produce the same table format as 3.1.

#### 3.3 Other Lazy-Loaded Relationships

Check if any other relationships exist (e.g., Group relationships, HostGroupAssoc back-references) and whether they are accessed in loops without eager loading.

#### 3.4 N+1 in Non-Relationship Patterns

Detect function calls inside loops that trigger additional queries (not via relationship lazy loading, but via explicit query calls):

| # | File:Line | Function | Called Inside Loop | Queries per Iteration | Status |
|---|-----------|----------|--------------------|----------------------|--------|
| 1 | `host_synchronize.py:NNN` | `_sync_group_data_for_org` | `get_group_using_host_id()` per host | 2 queries/host | **FAIL** |
| 2 | `group_repository.py:NNN` | `_update_hosts_for_group_changes` | `serialize_group(get_group_by_id_from_db())` per group_id | 1+ queries/group | **WARN** |
| 3 | `group_repository.py:NNN` | `serialize_group` | `get_non_culled_hosts_count_in_group()` per group | 1 count query/group | **WARN** |
| ... | ... | ... | ... | ... | ... |

**Status rules:**
- Relationship accessed with prior eager loading: **OK**
- Relationship accessed in loop WITHOUT eager loading: **FAIL**
- Query function called per item in loop: **FAIL** (if many items expected) or **WARN** (if bounded set)
- Count query per group in serialization: **WARN**

### Phase 4: Index Coverage Analysis

Map every filter/ORDER BY column to available indexes.

#### 4.1 Partition Pruning Check

For every query on partitioned tables (`hosts`, `hosts_groups`, `system_profiles_static`, `system_profiles_dynamic`), verify that `org_id` appears in the WHERE clause:

| # | File:Line | Function | Table | org_id in WHERE? | Status |
|---|-----------|----------|-------|------------------|--------|
| 1 | `host_query_db.py:NNN` | `_find_hosts_entities_query` | hosts | Yes | OK |
| 2 | `host_repository.py:NNN` | `host_query` | hosts | Yes | OK |
| ... | ... | ... | ... | ... | ... |

**Status rules:**
- org_id in WHERE clause (directly or via `host_query()` wrapper): **OK**
- org_id applied via OR across all org_ids (reaper pattern): **WARN** — partition pruning depends on query planner
- No org_id at all: **CRITICAL**

#### 4.2 WHERE Clause Index Coverage

For each filter column used in WHERE clauses, check if a matching index exists:

| Column / Expression | Used In | Index Available | Index Name | Status |
|---------------------|---------|----------------|------------|--------|
| `Host.org_id` | everywhere | PK (partitioned) | pk_hosts | OK |
| `Host.id` | everywhere | PK | pk_hosts | OK |
| `Host.modified_on` | ordering, date filters | Yes | `idx_hosts_modified_on_id` | OK |
| `Host.display_name` | `ilike()` filter | No dedicated index | — | **WARN** |
| `Host.fqdn` | `ilike()` filter | No dedicated index | — | **WARN** |
| `Host.insights_id` | canonical fact filter | Yes | `idx_hosts_insights_id` | OK |
| `Host.host_type` | system type filter | Yes (expression) | `idx_hosts_host_type` | OK |
| `Host.last_check_in` | staleness, ordering | Check | — | Check |
| `Host.tags` (containment) | tag filter | Yes (GIN) | `idx_hosts_groups_gin` or dedicated | OK |
| `Host.per_reporter_staleness` (JSONB path) | registered_with filter | No dedicated index | — | **INFO** |
| `Host.groups` (JSONB) | group ordering | Yes (GIN) | `idx_hosts_groups_gin` | OK |
| `Group.name` (with `func.lower()`) | group name filter | Check for lower() index | `idx_groups_org_id_name_ignorecase` | Check |
| `HostStaticSystemProfile.operating_system` | OS info, ordering | Yes (partial multi) | `idx_system_profiles_static_operating_system_multi` | OK |
| ... | ... | ... | ... | ... |

Include **every** filterable column — do not omit any.

**Status rules:**
- Index covers the exact filter pattern: **OK**
- `ilike('%...%')` on unindexed column (leading wildcard): **WARN** — cannot use B-tree; trigram/GIN needed
- JSONB path query without GIN index: **INFO** — may use containment index if structured correctly
- No index on frequently filtered column: **WARN**

#### 4.3 ORDER BY Index Coverage

| ORDER BY Column(s) | Used In | Index Covers Sort? | Status |
|--------------------|---------|-------------------|--------|
| `Host.modified_on DESC, Host.id DESC` | default ordering | Yes (`idx_hosts_modified_on_id`) | OK |
| `Host.display_name ASC` | order_by=display_name | No dedicated index | **WARN** |
| `Host.last_check_in` | order_by=last_check_in | Check | Check |
| `Host.groups[0]["name"]` | order_by=group_name | No (JSONB expression) | **INFO** |
| `HostStaticSystemProfile.operating_system` | order_by=operating_system | Via multi-column index | OK |
| ... | ... | ... | ... |

### Phase 5: Unbounded Query and Pagination Review

#### 5.1 Unbounded Result Sets

Detect queries that call `.all()` without a LIMIT clause on tables that could return large result sets:

| # | File:Line | Function | Table | Has LIMIT? | Has org_id? | Estimated Scale | Status |
|---|-----------|----------|-------|-----------|------------|-----------------|--------|
| 1 | `host_query_db.py:NNN` | `get_all_hosts` | hosts | **No** | Yes | All hosts in org | **FAIL** |
| 2 | `host_query_db.py:NNN` | `get_tag_list` | hosts | **No** | Yes | All hosts matching filters | **WARN** |
| 3 | `host_query_db.py:NNN` | `get_sap_sids_info` | hosts + SP dynamic | **No** | Yes | All SAP SIDs | **WARN** |
| 4 | `host_query_db.py:NNN` | `get_host_ids_list` | hosts | **No** | Yes | All host IDs matching filters | **WARN** |
| ... | ... | ... | ... | ... | ... | ... | ... |

For each FAIL/WARN, note the downstream impact:
- How the result is consumed (iterated, aggregated, returned to API, used for bulk delete)
- Memory implications for large orgs

**Status rules:**
- `.all()` without LIMIT on host-scale table: **FAIL** (could be millions of rows)
- `.all()` without LIMIT on bounded table (staleness, groups): **INFO**
- `.all()` followed by Python-side `islice()` pagination: **WARN** — loads all then slices

#### 5.2 Pagination Pattern Review

| # | File:Line | Function | Pattern | Scalable? | Status |
|---|-----------|----------|---------|-----------|--------|
| 1 | `host_query_db.py:NNN` | `_get_host_list_using_filters` | Flask `.paginate()` | Yes (OFFSET, capped per_page) | OK |
| 2 | `host_query_db.py:NNN` | `get_tag_list` | Python `islice()` on `.all()` | **No — loads all then slices** | **WARN** |
| 3 | `host_query_db.py:NNN` | `get_hosts_to_export` | `yield_per(batch_size)` | **Yes — streaming** | OK |
| 4 | `host_synchronize.py:NNN` | `_synchronize_hosts_for_org` | Keyset (`Host.id > last_id` + LIMIT) | **Yes** | OK |
| 5 | `lib/host_delete.py:NNN` | `delete_hosts` | `while count()` + `limit(chunk_size)` | Yes (chunked) | OK |
| ... | ... | ... | ... | ... | ... |

#### 5.3 In-Memory Aggregation

Detect queries that load full result sets and perform aggregation in Python instead of SQL:

| # | File:Line | Function | What Is Aggregated | Could Be SQL? | Status |
|---|-----------|----------|--------------------|---------------|--------|
| 1 | `host_query_db.py:NNN` | `_expand_host_tags` | JSONB tags to tag/count dicts | Partially (nested JSONB) | **WARN** |
| 2 | `host_query_db.py:NNN` | `get_sap_sids_info` | JSONB array elements to SID/count | Partially (could use SQL GROUP BY) | **WARN** |
| 3 | `host_query_db.py:NNN` | `get_tag_list` | Tag dedup + sort + search | Partially (regex prevents full SQL) | **INFO** |
| ... | ... | ... | ... | ... | ... |

### Phase 6: Bulk Operation Efficiency

#### 6.1 Individual Operations in Loops

Detect loops that perform individual INSERT, UPDATE, or DELETE operations:

| # | File:Line | Function | Operation | Loop Type | Batch Alternative | Status |
|---|-----------|----------|-----------|-----------|------------------|--------|
| 1 | `group_repository.py:NNN` | `_remove_hosts_from_group` | `_delete_host_group_assoc()` per assoc | for loop | Bulk `DELETE WHERE host_id IN (...)` | **WARN** |
| 2 | `group_repository.py:NNN` | `_update_hosts_for_group_changes` | `host.groups = ...` per host | for loop | Bulk `UPDATE SET groups = ... WHERE id IN (...)` | **WARN** |
| 3 | `host_synchronize.py:NNN` | `_sync_group_data_for_org` | `get_group_using_host_id()` + `session.add(host)` per host | for loop | JOIN query + bulk update | **WARN** |
| 4 | `lib/host_delete.py:NNN` | `_delete_host` | delete assoc + delete host per row | per host | ORM delete needed for event listeners | **INFO** |
| ... | ... | ... | ... | ... | ... | ... |

Note: Some individual operations are intentional because they need to fire SQLAlchemy event listeners (e.g., outbox event creation via `lib/host_outbox_events.py`). Bulk operations would bypass these listeners. Flag these as **INFO**, not WARN.

#### 6.2 Bulk Upsert Patterns

| # | File:Line | Function | Pattern | Status |
|---|-----------|----------|---------|--------|
| 1 | `host_app_repository.py:NNN` | `upsert_host_app_data` | `INSERT ... ON CONFLICT DO UPDATE` | OK |
| 2 | `group_repository.py:NNN` | `_add_hosts_to_group` | `db.session.add_all()` for new assocs | OK |
| ... | ... | ... | ... | ... |

#### 6.3 Session Management

| # | File:Line | Function | Pattern | Status |
|---|-----------|----------|---------|--------|
| 1 | `host_query_db.py:NNN` | `_get_host_list_using_filters` | `db.session.close()` after query | OK |
| 2 | `group_repository.py:NNN` | group operations | `session_guard(db.session)` context manager | OK |
| 3 | `host_delete.py:NNN` | `delete_hosts` | `session_guard` per chunk | OK |
| 4 | `host_synchronize.py:NNN` | `_sync_group_data_for_org` | `session.commit()` per chunk | OK |
| ... | ... | ... | ... | ... |

#### 6.4 count() Usage

Detect suboptimal `.count()` usage (generates `SELECT COUNT(*) FROM (subquery)`) vs optimized `func.count()`:

| # | File:Line | Function | Pattern | Status |
|---|-----------|----------|---------|--------|
| 1 | `host_query_db.py:NNN` | `_get_host_list_using_filters` | `func.count()` via `with_entities` | OK (optimized) |
| 2 | `host_reaper.py:NNN` | `run` | `query.count()` | **WARN** (subquery count on complex reaper query) |
| 3 | `host_delete.py:NNN` | `delete_hosts` | `select_query.count()` in while loop | **WARN** (repeated subquery count per iteration) |
| 4 | `host_repository.py:NNN` | `get_non_culled_hosts_count_in_group` | `query.count()` | INFO (small result set per group) |
| ... | ... | ... | ... | ... |

### Phase 7: Summary Report

#### Query Health Matrix

| Phase | Check | Result | CRITICAL | FAIL | WARN | INFO |
|-------|-------|--------|----------|------|------|------|
| 2 | Query pattern inventory | REPORT | — | — | — | N total queries |
| 3 | N+1 and lazy loading | PASS/FAIL | count | count | count | count |
| 4 | Index coverage | PASS/WARN | count | count | count | count |
| 5 | Unbounded queries | PASS/FAIL | count | count | count | count |
| 6 | Bulk operation efficiency | PASS/WARN | count | count | count | count |

#### Good Patterns Detected

Present a summary of positive patterns found:

| Pattern | Where | Details | Status |
|---------|-------|---------|--------|
| Conditional eager loading | `host_query_db.py:NNN` | Only `joinedload(SP)` when SP fields requested | OK |
| Deferred deprecated column | `host_query_db.py:NNN` | `defer(Host.system_profile_facts)` | OK |
| Column selection | `host_query_db.py:NNN` | `load_only()` when SP not needed | OK |
| Streaming export | `host_query_db.py:NNN` | `yield_per(batch_size)` for large exports | OK |
| Keyset pagination | `host_synchronize.py:NNN` | `Host.id > last_id` instead of OFFSET | OK |
| Bulk upsert | `host_app_repository.py:NNN` | `ON CONFLICT DO UPDATE` | OK |
| Duplicate join prevention | `db_filters.py:NNN` | `_is_table_already_joined()` | OK |
| Dynamic join detection | `db_filters.py:NNN` | `_needs_system_profile_joins()` | OK |
| In-memory host matching | `host_repository.py:NNN` | `find_existing_host()` from provided list | OK |
| Batch chunk processing | `host_delete.py:NNN` | Configurable chunk-based deletion | OK |
| Optimized count | `host_query_db.py:NNN` | `func.count()` instead of `.count()` | OK |

Include **all** good patterns found — this highlights the codebase's existing strengths.

#### Overall Status

Determine the overall verdict:
- **HEALTHY** — no CRITICAL or FAIL findings; only WARN/INFO
- **NEEDS ATTENTION** — FAIL findings exist that should be addressed
- **CRITICAL** — queries on partitioned tables missing org_id (full partition scan risk)

#### Consolidated Findings

Present ALL findings with WARN, FAIL, or CRITICAL status in a single table, ordered by severity:

| # | Phase | File:Line | Function | Status | Issue | Recommendation |
|---|-------|-----------|----------|--------|-------|----------------|
| 1 | description | `file.py:NNN` | function | CRITICAL/FAIL/WARN | what was found | what to do |
| ... | ... | ... | ... | ... | ... | ... |

If all checks passed, state: *"All query patterns are healthy — no findings."*

#### Action Items

List all findings ordered by severity and grouped by effort level:

**Quick Wins (low effort, high impact):**
- Items that can be fixed by adding `joinedload()` to existing queries
- Items that need a simple `LIMIT` clause

**Medium Effort:**
- Items requiring query restructuring (e.g., prefetching data before loops)
- Items requiring `.count()` optimization

**Larger Refactors:**
- Items requiring SQL-based aggregation to replace Python-side processing
- Items requiring bulk operation redesign (with event listener considerations)

For each action item, provide:
1. The specific file:line reference(s)
2. The issue description
3. The recommended code change

## Severity Rules

| Severity | Criteria |
|----------|----------|
| CRITICAL | Query on partitioned table without org_id filter (full table scan across ALL partitions) |
| CRITICAL | Unbounded DELETE/UPDATE without WHERE clause |
| FAIL | N+1 query: lazy-loaded relationship accessed in loop without eager loading |
| FAIL | Missing pagination on queries that could return thousands of rows per org |
| WARN | OFFSET pagination on large result sets (suggest keyset pagination) |
| WARN | Filter/ORDER BY on unindexed columns that are hot paths |
| WARN | In-memory aggregation that could be done in SQL |
| WARN | Individual ORM operations in a loop (vs bulk operation) |
| WARN | Repeated `.count()` calls on the same query (suggest tracking count arithmetically) |
| INFO | JSONB query without dedicated index (may use GIN containment index) |
| INFO | Intentional individual deletes (event listener dependency) |
| OK | Query follows best practices for the given use case |

## Important Notes

- This command is **read-only** — it analyzes query code but never modifies files or executes queries against the database.
- **Intentional individual deletes**: Some operations in `lib/host_delete.py` and `lib/group_repository.py` use individual ORM deletes (not bulk) intentionally because they need to fire SQLAlchemy event listeners for outbox event creation (`lib/host_outbox_events.py`). Do not flag these as FAIL — flag as **INFO** with a note about the event listener dependency.
- **Partitioned table queries**: HBI uses HASH partitioning by `org_id`. Queries without `org_id` in the WHERE clause force PostgreSQL to scan ALL partitions. The host reaper's `OR` across all org_ids is a known pattern — PostgreSQL may still prune partitions depending on the query planner. Flag as **WARN**, not CRITICAL.
- **In-memory tag aggregation**: The nested JSONB structure of `Host.tags` (`{namespace: {key: [values]}}`) makes pure SQL aggregation impractical. The Python-side aggregation in `_expand_host_tags` is a deliberate design choice. Flag the unbounded `.all()` as **WARN** (the real concern), not the Python-side processing itself.
- **`ilike('%...%')` patterns**: Leading-wildcard LIKE queries cannot use standard B-tree indexes. Trigram GIN indexes (`pg_trgm`) would help but add write overhead. Flag as **WARN** only if the endpoint is a known hot path (e.g., hostname search).
- **Flask `.paginate()` uses OFFSET internally**: This is acceptable for the API's typical page sizes (default 50, max 100) and is not flagged as a performance issue. Very high page numbers would degrade, but the API caps `per_page`.
- **`db.session.close()` after queries**: This pattern appears throughout `host_query_db.py`. It releases the connection back to the pool — good practice for read-only queries. Verify it does not interfere with lazy-loaded relationships that may be accessed after session close.
- **System identity join**: The `update_query_for_owner_id()` function adds an outerjoin to `HostStaticSystemProfile` for system identities (cert-auth). The `_is_table_already_joined()` check prevents duplicate joins. This is a correct pattern.
- **Kafka consumer in-memory matching**: The `find_existing_host()` function in `lib/host_repository.py` is called per message in the Kafka consumer, but uses in-memory matching from a prefetched host list when available (`_find_host_by_multiple_facts_in_db_or_in_memory()`). This is a well-designed optimization that reduces DB queries during batch processing. Do not flag as N+1.
- **`delete_hosts()` count loop**: The `while select_query.count()` pattern re-counts remaining rows before each batch. This is correct for ensuring completeness (rows may be re-added concurrently) but generates an additional query per iteration. The WARN is advisory — the alternative (tracking count arithmetically) would miss concurrent insertions.
- **`serialize_group()` count query**: The `get_non_culled_hosts_count_in_group()` call inside `serialize_group()` is a bounded N+1 risk — it only fires once per group in the response, not once per host. Flag as **WARN** when called in a loop over multiple groups, **INFO** for single-group serialization.
