# /hbi-migration - Migration Safety Review

Review an Alembic migration file for safety, correctness, and zero-downtime compatibility with HBI's partitioned table architecture. This command does NOT generate or run migrations — it analyzes existing migration files.

## Input

The migration to review is provided as: $ARGUMENTS

The argument can be **any of**:

1. **A file path** (e.g., `migrations/versions/abc123_add_column.py`) — used directly.
2. **A revision ID** (e.g., `abc123`) — resolved by searching `migrations/versions/` for a file containing `revision = "abc123"`.
3. **"latest"** or **empty** — resolves to the most recently modified migration file.

## Instructions

### Phase 0: Resolve Input

Determine which migration file to analyze:

1. If `$ARGUMENTS` is empty or `latest`:
   ```
   ls -t migrations/versions/*.py | head -1
   ```
   Use the result as the target file.

2. If `$ARGUMENTS` contains `/` or ends in `.py`: treat it as a file path. Verify the file exists by reading it. If not found, report the error and stop.

3. Otherwise, treat `$ARGUMENTS` as a revision ID. Search for it:
   ```
   grep -rl 'revision = "$ARGUMENTS"' migrations/versions/
   ```
   If no match is found, report *"No migration found with revision ID `<ID>`. Check `migrations/versions/` for the correct ID."* and stop.

Read the resolved migration file in full.

### Phase 1: Load Migration Context

Read these supporting files to establish context:

1. **`migrations/helpers.py`** — shared utilities: `TABLE_NUM_PARTITIONS`, `MIGRATION_MODE`, `session()`, `validate_num_partitions()`, `logger()`
2. **`migrations/env.py`** — `include_object()` filter rules, advisory lock pattern, schema isolation
3. **`app/models/constants.py`** — `INVENTORY_SCHEMA` constant definition
4. **`utils/partitioned_table_index_helper.py`** — `create_partitioned_table_index()` and `drop_partitioned_table_index()` functions for safe index management on partitioned tables

From the migration file, extract and present this overview:

#### Migration Overview

| Field | Value |
|-------|-------|
| Revision ID | *from `revision = "..."` line* |
| Down Revision | *from `down_revision = "..."` line* |
| Description | *docstring first line or migration message* |
| Tables Affected | *list of table names from `op.*` calls, `batch_alter_table()`, and raw SQL* |
| Operations | *ADD COLUMN, DROP COLUMN, CREATE INDEX, DROP INDEX, CREATE TABLE, DROP TABLE, ALTER COLUMN, INSERT, UPDATE, DELETE, RENAME, etc.* |
| Uses MIGRATION_MODE | *Yes/No — whether `MIGRATION_MODE` or `os.environ.get("MIGRATION_MODE"` or `os.getenv("MIGRATION_MODE"` appears* |
| Uses batch_alter_table | *Yes/No* |
| Uses partitioned_table_index_helper | *Yes/No — whether `create_partitioned_table_index` or `drop_partitioned_table_index` is imported or called* |
| Imports INVENTORY_SCHEMA | *Yes/No — from `app.models.constants` vs hardcoded `"hbi"`* |

To identify tables, look for these patterns in the migration body:
- `op.add_column("table_name", ...)` and `op.drop_column("table_name", ...)`
- `op.create_table("table_name", ...)`
- `op.drop_table("table_name")`
- `op.batch_alter_table("table_name", ...) as batch_op:`
- `op.create_index(..., "table_name", ...)`
- `op.drop_index(..., table_name="table_name")`
- `op.alter_column("table_name", ...)`
- `op.execute(...)` containing SQL with table names (look for `FROM`, `INTO`, `TABLE`, `INDEX ON`, `ALTER TABLE`)
- `create_partitioned_table_index(table_name="...")` and `drop_partitioned_table_index(table_name="...")`

### Phase 2: Partitioned Table Impact Analysis

HBI uses HASH partitioning by `org_id` on these core tables:

| Table | Composite PK | Notes |
|-------|-------------|-------|
| `hosts` | `(org_id, id)` | Main host inventory, highest row count |
| `hosts_groups` | `(org_id, host_id, group_id)` | Host-to-group associations |
| `system_profiles_static` | `(org_id, host_id)` | Denormalized static system profile data (~60 columns) |
| `system_profiles_dynamic` | `(org_id, host_id)` | Dynamic system profile data |

For each table the migration touches, determine whether it is in the partitioned table list above. Then evaluate every DDL/DML operation against the following checks:

#### 2.1 ADD COLUMN Checks

- **NOT NULL without `server_default`**: On a partitioned table, this triggers a full table rewrite across ALL partitions. Flag as **CRITICAL**.
- **NOT NULL with `server_default`**: Metadata-only change in PostgreSQL 11+ — **OK**.
- **Nullable column** (`nullable=True` or default): No rewrite needed — **OK**.
- On non-partitioned tables: `batch_alter_table` is the preferred pattern. If raw `op.add_column()` is used on a non-partitioned table instead, note as **INFO**.

#### 2.2 DROP COLUMN Checks

- Are there indexes that reference the dropped column? If yes and those indexes are NOT also dropped in the same migration: **WARN** — orphaned index definitions.
- Are there FK constraints referencing this column? If yes and not handled: **WARN**.
- Is the column part of a composite PK or partition key (`org_id`)? If yes: **CRITICAL** — never drop partition key columns.

#### 2.3 CREATE INDEX Checks

- On a partitioned table: Does it use `create_partitioned_table_index()` from `utils/partitioned_table_index_helper.py`? This helper handles the distinction between automated mode (direct creation) and managed mode (`CREATE INDEX CONCURRENTLY` per partition). If not using the helper:
  - Does the raw SQL use `CONCURRENTLY`? If no: **FAIL** — non-concurrent index creation on a partitioned table locks writes for the entire build duration.
  - If yes: **OK**, but note the helper is preferred for consistency.
- On a non-partitioned table: No special concern — **OK**.
- Expression indexes on JSONB paths (e.g., `system_profile_facts ->> 'host_type'`): Verify the path string is syntactically valid — **INFO**.

#### 2.4 Foreign Key Checks

- Does the FK include `org_id` as the first column? On partitioned tables, FKs MUST include the partition key. Missing `org_id`: **FAIL**.
- Does the FK column order match the target PK? E.g., `(org_id, host_id)` referencing `hosts(org_id, id)` — column order matters. Mismatch: **FAIL**.
- Does the FK use `ondelete="CASCADE"`? If referencing a partitioned table, CASCADE requires FK alignment with partition structure. Misaligned: **WARN**.
- Is the FK schema-qualified? Should use `f"{INVENTORY_SCHEMA}.hosts.org_id"` format — hardcoded `"hbi.hosts.org_id"`: **WARN**.

#### 2.5 DROP / RENAME TABLE Checks

- `ALTER TABLE ... RENAME TO`: Requires ACCESS EXCLUSIVE lock — **CRITICAL** for production downtime risk.
- `DROP TABLE`: Is this intentional? Is there a `MIGRATION_MODE` guard? Flag as **WARN** (or **CRITICAL** if dropping a core partitioned table).
- Does the `downgrade()` properly recreate the table with partitioning if applicable?

#### 2.6 Data Operation Checks (INSERT / UPDATE / DELETE)

- **Scale**: How many rows could be affected? Unbounded operations (no WHERE clause or LIMIT): **WARN**.
- **Idempotency**: Does it use `ON CONFLICT ... DO NOTHING` or `DO UPDATE`? Non-idempotent: **WARN**.
- **MIGRATION_MODE guard**: Is the operation inside a `MIGRATION_MODE == "automated"` conditional? Data operations on partitioned tables without this guard: **FAIL** (will run in production where external scripts should handle data).
- **Transaction size**: Could the operation process millions of rows in a single transaction? If yes: **WARN** — consider batching.

Present results:

| # | Table | Operation | Partitioned? | Check | Status | Details |
|---|-------|-----------|-------------|-------|--------|---------|
| 1 | hosts | ADD COLUMN | Yes | NOT NULL default | OK/CRITICAL | description |
| 2 | ... | ... | ... | ... | ... | ... |

### Phase 3: Zero-Downtime Compatibility

Evaluate whether this migration can run safely during a rolling deployment:

#### 3.1 Lock Analysis

Scan the migration for operations that acquire ACCESS EXCLUSIVE locks:
- `ALTER TABLE ... RENAME TO` / `RENAME CONSTRAINT`
- `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE`
- `ALTER TABLE ... ADD CONSTRAINT` with validation (non-deferrable)
- `ALTER TABLE ... ALTER COLUMN ... SET NOT NULL` (without `USING`)

If found: **CRITICAL** — these block all reads and writes on the table for the duration of the operation. Note the specific line(s).

#### 3.2 Long-Running Operations

Scan for potentially long-running operations inside the migration transaction:
- `INSERT INTO ... SELECT FROM` without `LIMIT` or `WHERE` bounds
- `UPDATE ... SET` without `WHERE` bounds
- `DELETE FROM` without `WHERE` bounds
- Data copy between tables (common in partition transition migrations)

If found without a `MIGRATION_MODE` guard: **FAIL** — will run in production and may take minutes/hours on large tables.
If found with a `MIGRATION_MODE == "automated"` guard: **OK** — only runs in dev/ephemeral environments.

#### 3.3 MIGRATION_MODE Handling

If the migration performs data operations on partitioned tables, verify:
1. It imports or reads `MIGRATION_MODE` (from `migrations.helpers` or `os.getenv("MIGRATION_MODE")`)
2. It conditionally executes data operations only in `automated` mode
3. It provides appropriate behavior in `managed` mode (either skip, stamp-only, or external script reference)

Missing `MIGRATION_MODE` check when needed: **FAIL**.
Present but incomplete (e.g., automated path only, no managed handling): **WARN**.

#### 3.4 Idempotency

Check all DDL/DML for idempotent patterns:
- `CREATE TABLE ... IF NOT EXISTS`
- `CREATE INDEX ... IF NOT EXISTS` or `CREATE INDEX CONCURRENTLY IF NOT EXISTS`
- `DROP TABLE IF EXISTS`
- `DROP INDEX IF EXISTS`
- `INSERT ... ON CONFLICT ... DO NOTHING`

Non-idempotent operations mean the migration cannot be safely re-run if it fails partway through: **WARN**.

#### 3.5 downgrade() Review

Check the `downgrade()` function:
- Is it implemented? (`pass` or empty body = no downgrade): **WARN** for schema changes, **INFO** for data-only changes.
- Does it properly reverse ALL operations in `upgrade()`?
- Does it handle `MIGRATION_MODE` if `upgrade()` does?
- Does it recreate dropped objects (tables, indexes, columns) with the correct structure?
- Does it handle partitioned table recreation if the upgrade drops or renames partitioned tables?

Present results:

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | ACCESS EXCLUSIVE locks | OK/CRITICAL | description |
| 2 | Long-running operations | OK/FAIL | description |
| 3 | MIGRATION_MODE handling | OK/WARN/FAIL | description |
| 4 | Idempotency | OK/WARN | description |
| 5 | downgrade() implementation | OK/WARN | description |

### Phase 4: Code Quality and Conventions

#### 4.1 Schema Constant

Check whether the migration uses `INVENTORY_SCHEMA` from `app.models.constants`:
- Imported and used: **OK**
- Hardcoded `"hbi"` or `schema="hbi"`: **WARN** — inconsistent with convention (though some existing migrations do this)
- No schema reference needed: **N/A**

#### 4.2 Shared Helpers

If the migration uses `TABLE_NUM_PARTITIONS`, `MIGRATION_MODE`, `session()`, `validate_num_partitions()`, or `logger()`:
- Imported from `migrations.helpers`: **OK**
- Re-defined locally (e.g., `int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))`): **WARN** — use the shared helper to keep behavior consistent

#### 4.3 Revision Chain

Validate the revision chain integrity:
1. Read the `down_revision` value from the migration
2. Search for a migration with that revision ID:
   ```
   grep -rl 'revision = "<down_revision_value>"' migrations/versions/
   ```
   If not found: **FAIL** — broken chain, migration cannot be applied.
3. Check for branching conflicts — other migrations with the same `down_revision`:
   ```
   grep -rl 'down_revision = "<down_revision_value>"' migrations/versions/
   ```
   If more than one file (including the current one) shares this `down_revision`: **FAIL** — revision conflict (branch point).

#### 4.4 Advisory Lock Usage

The advisory lock (`pg_advisory_lock(1)`) is managed by `migrations/env.py` and applies to ALL migrations. Individual migrations should NOT include their own advisory lock calls.
- If `pg_advisory_lock` appears in the migration body: **WARN** — redundant, potentially deadlocking.

#### 4.5 Unused Imports

Check the migration's import block for modules or functions that are not used in the migration body. Flag any as **INFO**.

Present results:

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | INVENTORY_SCHEMA usage | OK/WARN/N/A | description |
| 2 | Shared helpers | OK/WARN/N/A | description |
| 3 | Revision chain | OK/FAIL | description |
| 4 | Advisory lock | OK/WARN | description |
| 5 | Unused imports | OK/INFO | description |

### Phase 5: Security and Data Integrity

#### 5.1 Data Loss Operations

- **DROP COLUMN**: Is the column intentionally removed? Does the data need to be preserved or migrated elsewhere first? Flag as **WARN**.
- **DROP TABLE**: Is this a core table or a temporary/transitional table? Core partitioned table: **CRITICAL**. Transitional table (e.g., `hosts_old`): **INFO**.
- **TRUNCATE**: On any production table: **CRITICAL** unless inside `MIGRATION_MODE == "automated"` guard.

#### 5.2 FK Constraint Integrity

- **Adding FK**: Could existing data violate the new constraint? If the FK is added with `NOT VALID` and then validated separately: **OK**. If added with immediate validation on a large table: **WARN** — may fail or lock.
- **Dropping FK**: Could this allow orphaned records going forward? Flag as **WARN** and note the implication.

#### 5.3 Uniqueness Constraints

- **INSERT operations**: Could they violate existing unique constraints? Without `ON CONFLICT`: **WARN** — migration will fail on duplicate data.
- **Adding UNIQUE constraint**: On existing data that may have duplicates: **WARN** — will fail if duplicates exist.

#### 5.4 Auth and Tenant Isolation

- **Modifying `org_id`**: Any ALTER COLUMN, DROP, or type change on `org_id` columns: **CRITICAL** — this is the partition key and tenant isolation boundary.
- **Modifying identity-related columns** (`insights_id`, `subscription_manager_id`, `provider_id`): These are canonical facts used for host deduplication. Changes require careful coordination: **WARN**.

Present results:

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | Data loss operations | OK/WARN/CRITICAL | description |
| 2 | FK constraint integrity | OK/WARN | description |
| 3 | Uniqueness constraints | OK/WARN | description |
| 4 | Auth/tenant column safety | OK/WARN/CRITICAL | description |

### Phase 6: Summary Report

Compile all findings into a final report.

#### Overall Safety Rating

Determine the rating based on the highest severity finding across all phases:

- **SAFE** — all checks passed with OK or INFO only
- **CAUTION** — WARN findings exist but no FAIL or CRITICAL
- **UNSAFE** — FAIL or CRITICAL findings exist that should be addressed before merging

#### Consolidated Findings

Present ALL findings from Phases 2-5 in a single table:

| # | Phase | Check | Status | Details | Recommendation |
|---|-------|-------|--------|---------|----------------|
| 1 | Partitioned Tables | description | OK/WARN/FAIL/CRITICAL | what was found | what to do |
| 2 | Zero-Downtime | description | OK/WARN/FAIL/CRITICAL | what was found | what to do |
| ... | ... | ... | ... | ... | ... |

Only include findings with WARN, FAIL, or CRITICAL status. If all checks passed, state: *"All checks passed — no findings."*

#### Test Plan

Generate a test plan specific to the operations found in this migration:

**Always include:**
- [ ] Run `make upgrade_db` in local dev environment
- [ ] Run downgrade to verify reversibility: `FLASK_APP=manage.py flask db downgrade -1`
- [ ] Run `pipenv run pytest --cov=.` to verify tests pass

**For ADD COLUMN operations:**
- [ ] Verify column exists after migration: connect to db and run `\d hbi.<table_name>`

**For CREATE INDEX operations:**
- [ ] Verify index exists: `\di hbi.<index_name>`
- [ ] Run a query that should use the new index and verify with `EXPLAIN`

**For DROP operations:**
- [ ] Verify object is removed
- [ ] Verify dependent queries/code still works

**For data operations (INSERT/UPDATE/DELETE):**
- [ ] Check row counts before and after the migration
- [ ] Verify data integrity with a spot check query

**For MIGRATION_MODE migrations:**
- [ ] Test in automated mode (default): `make upgrade_db`
- [ ] Test in managed mode: `MIGRATION_MODE=managed make upgrade_db`

## Important Notes

- This command is **read-only** — it analyzes migration files but never modifies them.
- This command does NOT generate migrations. Use `make migrate_db message="..."` for that.
- This command does NOT run migrations. Use `make upgrade_db` or `make hbi-migrate` for that.
- The partitioned table list may change over time. If a table is not in the known list, check `migrations/versions/` for its creation migration to determine if it is partitioned.
- Some findings (like hardcoded schema `"hbi"`) are convention preferences, not bugs. Several existing migrations use both patterns.
- The `MIGRATION_MODE` dual-mode pattern is only required for migrations that perform **data operations** on partitioned tables. Schema-only changes (ADD/DROP COLUMN, CREATE INDEX) do not need it — though CREATE INDEX on partitioned tables should still use the `create_partitioned_table_index()` helper.
- For migrations using `create_partitioned_table_index()`, read `utils/partitioned_table_index_helper.py` to understand how it handles automated vs managed mode (direct creation vs `CONCURRENTLY` per partition).
- The advisory lock in `migrations/env.py` (`pg_advisory_lock(1)`) prevents concurrent migrations automatically — individual migration files should NOT include their own advisory locks.
