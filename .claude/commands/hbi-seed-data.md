# /hbi-seed-data - Seed HBI Database with Sample Data via Kafka

Populate the HBI development database with sample hosts and application data using the **real Kafka ingestion pipeline**. Hosts are created via `platform.inventory.host-ingress` and app data via `platform.inventory.host-apps` — the same message flow used in production.

## Input

The action to perform is provided as: $ARGUMENTS

Supported actions:
- **(empty)** — seed 5 default hosts + all app data for org `321`
- **`<count> [org_id]`** — seed N hosts (1–50) + all app data (e.g., `10` or `10 my_org`)
- **`hosts [count] [type] [org_id]`** — seed only hosts, no app data (e.g., `hosts 10 sap my_org`)
- **`app-data [org_id]`** — populate app data for existing hosts in an org (default org: `321`)
- **`full <count> [type] [org_id]`** — seed N hosts + app data with explicit host type (e.g., `full 20 rhsm my_org`)
- **`clean [org_id]`** — remove all data for an org (default org: `321`)
- **`status`** — show current seed data stats across orgs
- **`help`** — print this list of supported actions with examples

**Global parameter:** All seeding actions accept an optional `org_id` as their last positional argument. If omitted, defaults to `321` (matching `INVENTORY_HOST_ACCOUNT` in `utils/payloads.py`).

## Instructions

### Phase 1: Verify Prerequisites

Before any seeding, verify the database and MQ services are reachable:

**Check 1 — Database connectivity:**
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c "SELECT 1;"
```

If this fails, report: "Database is not reachable. Is the dev environment running? Try `make hbi-up`." and stop.

**Check 2 — hbi-mq consumer services:**
```bash
podman compose -f dev.yml ps --format '{{.Name}} {{.Status}}' | grep -E 'hbi-mq|hbi-mq-apps'
```

If `hbi-mq` is not running, report: "The hbi-mq consumer service is not running. It must be running to process host-ingress messages. Start it with `make hbi-up` or `podman compose -f dev.yml up -d hbi-mq`." and stop.

If `hbi-mq-apps` is not running, warn: "The hbi-mq-apps consumer service is not running. App data messages on `platform.inventory.host-apps` will not be consumed. Start it with `podman compose -f dev.yml up -d hbi-mq-apps`." If the action involves app data (Default, Full, or App Data Only), stop. Otherwise continue with a warning.

**Note:** Two MQ consumer services handle different Kafka topics: `hbi-mq` consumes `platform.inventory.host-ingress` (host creation/updates), and `hbi-mq-apps` consumes `platform.inventory.host-apps` (application data). Both must be running for full seed data functionality.

### Phase 2: Route Action

Parse `$ARGUMENTS` to determine which action to run:

- If empty or blank → **Default** (seed 5 hosts + app data, org `321`)
- If a plain integer (1–50), optionally followed by an org_id → **Default with count** (seed N hosts + app data)
- If starts with `hosts` → **Hosts Only** (extract optional count, type, and org_id tokens)
- If starts with `app-data` → **App Data Only** (extract optional org_id)
- If starts with `full` → **Full** (extract count, optional type, and optional org_id)
- If starts with `clean` → **Clean** (extract optional org_id)
- If equals `status` → **Status**
- If equals `help` → **Help**
- Otherwise → report unrecognized action and list available actions

**Org ID detection heuristic:** When parsing trailing tokens, if a token is not a recognized host type (`default`, `rhsm`, `qpc`, `sap`) and is not a plain integer, treat it as `org_id`.

**Validation:**
- If count is provided and > 50, reject: "Maximum 50 hosts per invocation. For larger datasets, run the command multiple times."
- If count is provided and < 1 or non-numeric, reject: "Count must be a positive integer (1–50)."
- Valid host types: `default`, `rhsm`, `qpc`, `sap` (matching `utils/kafka_producer.py`)

---

### Action: Default / Full (seed hosts + app data)

**Parameters:**
- `count`: number of hosts (default: 5)
- `type`: host type (default: `default`)
- `org_id`: defaults to `321` (the `INVENTORY_HOST_ACCOUNT` from `utils/payloads.py`)

**Step 1 — Record baseline host count:**
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c \
  "SELECT COUNT(*) FROM hbi.hosts WHERE org_id = '<org_id>';"
```
Save this as `baseline_count`.

**Step 2 — Produce hosts via Kafka:**

The `utils/payloads.py` reads `INVENTORY_HOST_ACCOUNT` at import time to set the org_id in all payloads and identity headers. Set this env var to the desired org_id:
```bash
unset PIPENV_PIPFILE && INVENTORY_HOST_ACCOUNT='<org_id>' pipenv run python utils/kafka_producer.py --num-hosts <count> --host-type <type>
```

**Step 3 — Wait for ingestion:**

Poll the database every 2 seconds for up to 30 seconds until new hosts appear:
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c \
  "SELECT COUNT(*) FROM hbi.hosts WHERE org_id = '<org_id>';"
```
Wait until the count is at least `baseline_count + count`. If 30 seconds elapse without reaching the target, warn: "Ingestion timeout — only N of M expected hosts appeared. Check `podman compose -f dev.yml logs hbi-mq` for consumer errors."

**Step 4 — Retrieve new host IDs:**
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c \
  "SELECT id FROM hbi.hosts WHERE org_id = '<org_id>' ORDER BY created_on DESC LIMIT <count>;"
```
Save the returned UUIDs (one per line).

**Step 5 — Produce app data via Kafka:**
```bash
unset PIPENV_PIPFILE && pipenv run python utils/kafka_app_data_producer.py \
  --org-id <org_id> \
  --host-ids <uuid1> <uuid2> ... <uuidN>
```
This sends 6 messages (one per app type: advisor, vulnerability, patch, remediations, compliance, malware), each containing data for all the seeded hosts.

**Step 6 — Wait for app data ingestion:**

Poll the database every 2 seconds for up to 15 seconds:
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c \
  "SELECT COUNT(*) FROM hbi.hosts_app_data_advisor WHERE org_id = '<org_id>';"
```
Wait until the count shows the new entries have been processed.

**Step 7 — Report summary:**

Query final counts:
```sql
SELECT 'hosts' AS table_name, COUNT(*) AS count FROM hbi.hosts WHERE org_id = '<org_id>'
UNION ALL SELECT 'advisor', COUNT(*) FROM hbi.hosts_app_data_advisor WHERE org_id = '<org_id>'
UNION ALL SELECT 'vulnerability', COUNT(*) FROM hbi.hosts_app_data_vulnerability WHERE org_id = '<org_id>'
UNION ALL SELECT 'patch', COUNT(*) FROM hbi.hosts_app_data_patch WHERE org_id = '<org_id>'
UNION ALL SELECT 'remediations', COUNT(*) FROM hbi.hosts_app_data_remediations WHERE org_id = '<org_id>'
UNION ALL SELECT 'compliance', COUNT(*) FROM hbi.hosts_app_data_compliance WHERE org_id = '<org_id>'
UNION ALL SELECT 'malware', COUNT(*) FROM hbi.hosts_app_data_malware WHERE org_id = '<org_id>';
```

Present as:
```
| Table | Count |
|-------|-------|
| hosts | N |
| advisor | N |
| vulnerability | N |
| patch | N |
| remediations | N |
| compliance | N |
| malware | N |
```

---

### Action: Hosts Only

**Parameters:**
- `count`: number of hosts (default: 5, from second token)
- `type`: host type (default: `default`, from third token)
- `org_id`: from fourth token, or third if it's not a recognized host type (default: `321`)

Run Steps 1–3 from the Default action only (no app data), using the resolved `org_id`. Set `INVENTORY_HOST_ACCOUNT='<org_id>'` when calling `kafka_producer.py`. Report how many hosts were created and their IDs.

Show a hint: "To add app data for these hosts, run `/hbi-seed-data app-data <org_id>`."

---

### Action: App Data Only

**Parameters:**
- `org_id`: from second token (default: `321`)

**Step 1 — Query existing host IDs:**
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c \
  "SELECT id FROM hbi.hosts WHERE org_id = '<org_id>' LIMIT 50;"
```

If no hosts are found, report: "No hosts found for org_id `<org_id>`. Create hosts first with `/hbi-seed-data hosts`." and stop.

**Step 2 — Produce app data:**
```bash
unset PIPENV_PIPFILE && pipenv run python utils/kafka_app_data_producer.py \
  --org-id <org_id> \
  --host-ids <uuid1> <uuid2> ... <uuidN>
```

**Step 3 — Wait and report** (same as Default Steps 6–7, using the provided org_id).

---

### Action: Clean

**Parameters:**
- `org_id`: from second token (default: `321`)

**Safety check:** If `org_id` does not start with a number or looks like a production org (longer than 10 characters), use `AskUserQuestion` to confirm: "Are you sure you want to delete ALL hosts and app data for org_id `<org_id>`? This cannot be undone."

**Execute:**
```bash
podman compose -f dev.yml exec -T db psql -U insights -d insights -c \
  "DELETE FROM hbi.hosts WHERE org_id = '<org_id>';"
```

The `ON DELETE CASCADE` foreign key constraints on `hosts_app_data_*` tables will automatically clean up associated app data.

Report how many hosts were deleted (from the `DELETE N` output).

---

### Action: Status

Query counts across all tables for orgs that have data:

```sql
SELECT
    h.org_id,
    h.host_count,
    COALESCE(a.cnt, 0) AS advisor,
    COALESCE(v.cnt, 0) AS vulnerability,
    COALESCE(p.cnt, 0) AS patch,
    COALESCE(r.cnt, 0) AS remediations,
    COALESCE(c.cnt, 0) AS compliance,
    COALESCE(m.cnt, 0) AS malware
FROM (SELECT org_id, COUNT(*) AS host_count FROM hbi.hosts GROUP BY org_id) h
LEFT JOIN (SELECT org_id, COUNT(*) AS cnt FROM hbi.hosts_app_data_advisor GROUP BY org_id) a ON h.org_id = a.org_id
LEFT JOIN (SELECT org_id, COUNT(*) AS cnt FROM hbi.hosts_app_data_vulnerability GROUP BY org_id) v ON h.org_id = v.org_id
LEFT JOIN (SELECT org_id, COUNT(*) AS cnt FROM hbi.hosts_app_data_patch GROUP BY org_id) p ON h.org_id = p.org_id
LEFT JOIN (SELECT org_id, COUNT(*) AS cnt FROM hbi.hosts_app_data_remediations GROUP BY org_id) r ON h.org_id = r.org_id
LEFT JOIN (SELECT org_id, COUNT(*) AS cnt FROM hbi.hosts_app_data_compliance GROUP BY org_id) c ON h.org_id = c.org_id
LEFT JOIN (SELECT org_id, COUNT(*) AS cnt FROM hbi.hosts_app_data_malware GROUP BY org_id) m ON h.org_id = m.org_id
ORDER BY h.host_count DESC
LIMIT 20;
```

Present as a table. If no data exists, report: "No hosts in the database. Run `/hbi-seed-data` to create sample data."

---

### Action: Help

Print a summary of all supported actions with usage examples. No prerequisites or database access required.

Present the following to the user:

```
/hbi-seed-data — Seed HBI Database with Sample Data via Kafka

Supported actions:

  (no args)              Seed 5 default hosts + all app data for org 321
  <count> [org_id]       Seed N hosts (1–50) + all app data
  hosts [count] [type] [org_id]
                         Seed only hosts, no app data
  app-data [org_id]      Populate app data for existing hosts
  full <count> [type] [org_id]
                         Seed N hosts + app data with explicit host type
  clean [org_id]         Remove all data for an org
  status                 Show current seed data stats across orgs
  help                   Print this help message

Host types: default, rhsm, qpc, sap
Default org_id: 321

Examples:
  /hbi-seed-data                     # 5 default hosts + app data, org 321
  /hbi-seed-data 10                  # 10 hosts + app data, org 321
  /hbi-seed-data 10 my_org           # 10 hosts + app data, org my_org
  /hbi-seed-data hosts 20 sap        # 20 SAP hosts only, no app data
  /hbi-seed-data app-data my_org     # app data for existing hosts in my_org
  /hbi-seed-data full 15 rhsm        # 15 RHSM hosts + app data
  /hbi-seed-data clean               # delete all data for org 321
  /hbi-seed-data status              # show data stats across all orgs
```

---

## Important Notes

- **Real Kafka pipeline**: This command uses the production-equivalent message ingestion path. Hosts flow through `platform.inventory.host-ingress` → `hbi-mq` consumer → PostgreSQL. App data flows through `platform.inventory.host-apps` → `hbi-mq-apps` consumer → PostgreSQL.
- **Two MQ consumers must be running**: `hbi-mq` consumes host-ingress messages, `hbi-mq-apps` consumes host-apps messages. If either is not running, the corresponding messages sit in Kafka unprocessed.
- **Custom org_id**: All seeding actions accept an optional `org_id` as the last positional argument (e.g., `/hbi-seed-data 10 my_org`). When provided, it is passed as `INVENTORY_HOST_ACCOUNT='<org_id>'` to `kafka_producer.py` (which uses it for both the host payload and the `b64_identity` header) and as `--org-id <org_id>` to `kafka_app_data_producer.py`. If omitted, defaults to `321`.
- **How org_id flows through the pipeline**: `utils/payloads.py` reads `INVENTORY_HOST_ACCOUNT` at module import time and encodes it into both the host data and the Base64 identity header. The MQ consumers validate that the org_id in the identity matches the org_id in the payload — so both must agree.
- **Host types**: `default` (standard with system profiles), `rhsm` (Red Hat Subscription Manager), `qpc` (Quipucords Product Catalog), `sap` (SAP workloads).
- **Ingestion delay**: There is a small delay (typically 1–5 seconds) between producing a Kafka message and seeing the data in PostgreSQL. The command polls the DB to wait for completion.
- **Idempotency**: Running the command multiple times creates additional hosts (each with a unique `insights_id`). App data uses `ON CONFLICT DO UPDATE`, so re-seeding refreshes existing entries.
- **Cascading deletes**: The `clean` action only needs `DELETE FROM hbi.hosts` — foreign key constraints with `ON DELETE CASCADE` automatically remove associated `hosts_app_data_*`, `hosts_groups`, `system_profiles_static`, and `system_profiles_dynamic` rows.
- **Development database only**: This command targets the local Podman-managed PostgreSQL. Never use against production.
