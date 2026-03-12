# HBI Operations & Tracing - Face to Face

---

## Session 1: State of Operations Today (09:30 - 11:00)

**Co-lead: Asa Price, Rodrigo Antunes**

---

### Slide 1 - HBI Architecture Overview

```
                        ┌──────────────┐
                        │   Clients    │
                        └──────┬───────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
         ┌──────▼──────┐ ┌────▼────┐ ┌───────▼───────┐
         │  Web Service │ │   MQ    │ │    Export      │
         │  (Flask +    │ │ Service │ │    Service     │
         │   Gunicorn)  │ │ (Kafka  │ │               │
         │              │ │consumer)│ │               │
         └──────┬───────┘ └────┬────┘ └───────┬───────┘
                │              │              │
                └──────────────┼──────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    PostgreSQL        │
                    │  (32 hash partitions │
                    │   on org_id)         │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Read Replica       │
                    │  (reporting/queries) │
                    └─────────────────────┘
```

- **Web Service**: Flask REST API for inventory CRUD operations
- **MQ Service**: Kafka consumer processing host create/update messages
- **Export Service**: Bulk data extraction for downstream consumers
- **Host Reaper**: Background job that cleans up stale/culled hosts
- **Infrastructure**: PostgreSQL (partitioned), Kafka, Redis (via Clowder)

> **Speaker notes**: Walk through the request flow -- API calls come in through the web service, host updates arrive via Kafka, both write to the same partitioned PostgreSQL database. The read replica handles reporting workloads.

---

### Slide 2 - How We Deploy

- **Platform**: OpenShift via Clowder (cloud.redhat.com infrastructure)
- **Configuration**: `deploy/clowdapp.yml` defines all deployments, jobs, and dependencies
- **Database migrations**: Alembic migrations run as a CJI (ClowdJobInvocation) before app deployment (`deploy/cji.yml`)
- **Feature flags**: Unleash for progressive rollouts
- **Release pipeline**:
  1. PR -> CI tests -> merge to master -> **automatically deployed to stage**
  2. Run the stage test pipeline to validate
  3. Trigger prod release via `app-interface-bot` GitLab pipeline (select `HMS_SERVICE=host-inventory`, set git hash)
  4. The bot collects all GitHub commits and descriptions since the last release and generates an MR to `app-interface` with a full changelog
  5. MR review -> merge -> deployed to prod

> **Speaker notes**: Emphasize the CJI pattern for migrations -- this is important context for the index changes we'll discuss later. Migrations run as a separate job before the app pods restart. Show the `app-interface-bot` pipeline screenshot -- this is how we trigger releases. The bot automates the changelog generation by collecting all commit messages between the previous and new git hash, which makes release MRs self-documenting.

---

### Slide 3 - Production Scale

| Metric | Value |
|--------|-------|
| Total hosts | ~5 million |
| Primary DB instance | AWS RDS `db.m7g.8xlarge` (32 vCPUs, 128 GB RAM) |
| Read replica | Same instance type, used for reporting |
| Table partitioning | 32 hash partitions on `hosts` and `hosts_groups` |
| Total DB size (estimated) | ~500+ GB including indexes |

> **Speaker notes**: The scale matters for understanding why certain optimizations have outsized impact. At 5M hosts, a missing index or a full sequential scan has very different consequences than with 10K hosts locally.

---

### Slide 4 - Current Observability Stack

**What we HAVE:**
- Prometheus metrics (request counts, latencies, error rates)
- 2 Grafana dashboards: General inventory metrics + Cyndi metrics
- Structured JSON logging with request IDs
- `prometheus-flask-exporter` for automatic HTTP metrics
- Alerting to Slack: `#team-consoledot-inventory` > `HBI Alerts` channel
  - Container restart alerts (prod deployments)
  - MQ consumer error rate alerts (FIRING / RESOLVED)
  - Host App data ingest failure rate alerts (stage + prod)
  - Each alert includes: Query, Dashboard, Alert Definition, and Silence links

**What we're MISSING:**
- No distributed tracing
- No per-query SQL visibility (we see overall latency, not which query is slow)
- No request-level breakdown (DB time vs. serialization vs. network)
- No cross-service correlation (can't follow a request from API -> Kafka -> downstream)

```
 Metrics tell us WHAT is happening     Traces tell us WHY it's happening
 ─────────────────────────────────     ─────────────────────────────────
 "P99 latency is 2.3s"                "This request took 2.3s because
                                       the host list query did a seq scan
                                       on a 200K-row partition"
```

> **Speaker notes**: Walk through the Slack alert channel screenshot -- show the team that we do have alerting for critical failures (container restarts, MQ errors, ingest failures), but these are reactive and coarse-grained. We know something broke, but not why. This is the core gap: we have good high-level metrics but when something is slow, we can't drill down. When a customer reports a slow experience, we can check dashboards but can't trace their specific request.

---

### Slide 5 - What We Cannot Answer Today

| Question | Why we can't answer it |
|----------|----------------------|
| Which API endpoint is slowest for a specific org? | No per-request tracing with org_id context |
| Is the bottleneck in SQL, serialization, or network? | No breakdown within a request |
| How does a Kafka message flow through ingestion? | No trace correlation across MQ -> DB -> event |
| What was a specific customer's request execution path? | No way to filter by identity/org |
| Which SQL queries are executed for a given endpoint? | No SQL-level instrumentation |

> **Speaker notes**: These are the questions tracing will answer. Transition into Session 2 where we'll show how.

---
---

## Session 2: Tracing Benefits / Areas of Improvement (11:15 - 12:30)

**Co-lead: Asa Price, Rodrigo Antunes**

---

### Slide 6 - What is Distributed Tracing?

**Core concepts:**

- **Trace**: The complete journey of a single request through the system
- **Span**: A single operation within a trace (e.g., one SQL query, one HTTP call)
- **Context propagation**: Passing trace IDs between services so spans are linked

```
Trace: GET /api/hosts
│
├── Span: Flask request handler (45ms)
│   ├── Span: SQLAlchemy query - host list (28ms)
│   │   └── Span: PostgreSQL execution (25ms)
│   ├── Span: SQLAlchemy query - count (12ms)
│   │   └── Span: PostgreSQL execution (10ms)
│   └── Span: Serialization (3ms)
│
└── Total: 45ms (28ms DB + 12ms DB + 3ms app + 2ms overhead)
```

Each span carries:
- Operation name and duration
- Custom attributes (e.g., `hbi.org_id`, `hbi.request_id`)
- Status (OK / ERROR) and exception details
- Parent-child relationships

> **Speaker notes**: The key insight is that a trace is a tree. You can see not just that a request took 45ms, but exactly where those 45ms were spent. This is impossible with metrics alone.

---

### Slide 7 - OpenTelemetry: The Standard

- **What**: CNCF project -- the industry standard for observability instrumentation
- **Vendor-neutral**: Instrument once, export to any backend
- **Auto-instrumentation**: Libraries exist for all HBI technologies:

| Component | OTel Library | What it captures |
|-----------|-------------|-----------------|
| Flask | `opentelemetry-instrumentation-flask` | HTTP requests, status codes, routes |
| SQLAlchemy | `opentelemetry-instrumentation-sqlalchemy` | Every SQL query with text and duration |
| Requests | `opentelemetry-instrumentation-requests` | Outbound HTTP calls (RBAC, etc.) |
| Kafka | `opentelemetry-instrumentation-confluent-kafka` | Message produce/consume spans |

- **Backend**: Grafana Tempo (already in our Grafana stack) for trace storage and querying
- **Protocol**: OTLP (OpenTelemetry Protocol) over HTTP

> **Speaker notes**: The important point is that OTel is not a vendor lock-in. We instrument with the standard SDK, and if we ever change our trace backend, we just change the exporter config. The instrumentation code stays the same.

---

### Slide 8 - What We Built on the Day of Learning

**Phase 1 implementation** (working prototype on a feature branch):

| Component | What was done |
|-----------|--------------|
| `app/telemetry.py` | Central module: `init_otel()`, Flask/SQLAlchemy/HTTP instrumentation |
| `gunicorn.conf.py` | `post_fork` hook to initialize OTel per Gunicorn worker |
| `run.py` | Direct `init_otel()` for single-process dev mode |
| `inv_mq_service.py` | OTel init for the Kafka consumer service |
| `app/queue/host_mq.py` | Manual `mq.batch` and `mq.process` spans for message processing |
| `dev.yml` | Added Grafana Tempo + Grafana services for local tracing |

**Custom attributes on every span:**
- `hbi.org_id` -- extracted from `x-rh-identity` header
- `hbi.request_id` -- extracted from `x-rh-insights-request-id` header

**SQLCommenter**: Trace context is embedded as comments in SQL queries, enabling correlation between traces and database logs.

> **Speaker notes**: This took about a day to implement. The key design decision was initializing OTel in `post_fork` for Gunicorn's multi-worker model, and using custom request hooks to extract our identity headers into span attributes.

---

### Slide 9 - Live Demo: Traces in Grafana Tempo

**Pre-demo setup** (run before the session or during the break):
```bash
./scripts/demo-tracing.sh
```

This script automatically:
1. Starts all containers (DB, Kafka, Tempo, Grafana, HBI web + MQ)
2. Runs database migrations
3. Ingests 100 hosts via Kafka (generates `mq.batch` traces)
4. Makes 7 API requests with distinct `x-rh-insights-request-id` values (generates Flask + SQL traces)

**Live demo flow in Grafana** (`http://localhost:3000` -> Explore -> Tempo):

1. **Search by service name**: `host-inventory` -- show all recent traces
2. **Find the MQ batch trace**: look for `mq.batch` -- expand to show per-message child spans
3. **Find a GET /hosts trace**: expand the waterfall to show nested SQL query spans
4. **Click on a SQL span**: show the actual query text, duration, and database attributes
5. **Filter by org_id**: attribute `hbi.org_id = 0000001`
6. **Filter by request_id**: attribute `hbi.request_id = demo-list-hosts-001`
7. **Compare traces**: sort by duration -- the `per_page=100` request should be slower than `per_page=50`

**What to point out:**
- The waterfall view shows the full request timeline
- Each SQL query appears as a child span with the actual query text
- The `hbi.org_id` attribute is visible on the root span
- You can see exactly how much time is DB vs. application logic
- Error spans are highlighted in red with exception details

> **Speaker notes**: Run `./scripts/demo-tracing.sh` during the 11:00 break so everything is warm when you start this session. Walk through the Grafana UI live -- the visual impact of seeing the span waterfall is the most compelling part of the presentation. If something goes wrong with the live demo, use `./scripts/demo-tracing.sh --quick` to re-seed data without rebuilding.

---

### Slide 10 - Gaps Tracing Closes

| Gap Today | How Tracing Closes It |
|-----------|----------------------|
| "Which SQL query is slow?" | SQLAlchemy spans show every query with exact duration |
| "Is it the DB or app logic?" | Span tree shows time in DB vs. serialization vs. framework |
| "What happened for this customer?" | Filter traces by `hbi.org_id` to find their specific requests |
| "How does MQ ingestion perform?" | Batch spans wrap all messages; per-message child spans show individual processing |
| "Why is this endpoint slow only for large orgs?" | Compare traces across org_ids, spot query plan differences |
| "Cross-service request flow?" | W3C `traceparent` header propagation links spans across services |

> **Speaker notes**: For each gap, give a concrete example from our experience. E.g., "Last sprint we had a report of slow host listing -- with tracing, we could have filtered by the customer's org_id and immediately seen which SQL query was the bottleneck."

---

### Slide 11 - What We Found Using Traces + DB Analysis

The Day of Learning tracing work led us to investigate production query patterns. Here's what we confirmed:

**Missing `org_id` in join conditions (biggest finding):**
- Every query that joins `hosts_groups` is missing `org_id` in the join condition
- Since `hosts_groups` is partitioned by `HASH(org_id)`, PostgreSQL **scans all 32 partitions** instead of just 1
- The current #1 AAS query (group listing) scans ~2.7M rows across all partitions for a query that only needs 1 partition
- This affects **every endpoint** that touches groups: host listing, group listing, system profile, filtered queries
- Fix: add `org_id` to all 8 join sites -- **code-only change, no migration, ~97% reduction in scanned data**

**Dead weight consuming resources:**
- `hosts_old` table: ~361 GB, never queried
- Zero-scan indexes: ~1.3 GB (GIN on groups, GIN on workloads, redundant org_id)
- These consume buffer cache space, competing with active data

**Query patterns that could be optimized:**
- `jsonb_build_object` assembling system profile JSON in PostgreSQL instead of Python
- SAP aggregation endpoint executing two queries when one would suffice
- Staleness configuration fetched from DB on every request (could be cached)

> **Speaker notes**: The partition pruning fix is the star of this slide. Show the EXPLAIN output: 32 seq scans on a table partitioned by org_id, just because the join condition uses group_id without org_id. It's a one-line code fix per join site with massive impact. This is exactly the kind of issue that tracing and query analysis surfaces.

---

### Slide 12 - Proposed Optimizations

| Priority | Optimization | Estimated Impact | Status |
|----------|-------------|-----------------|--------|
| P1 | Add `org_id` to all `hosts_groups` join conditions | **~97% reduction** in scanned data on every group-related query. Fixes #1 AAS query. Code-only, no migration. | **New ticket** |
| P2 | Drop `hosts_old` table | ~361 GB freed, reduced backup time | RHINENG-24456 |
| P3 | Drop zero-scan indexes | ~1.3 GB freed, less buffer cache waste | RHINENG-24458 (Release Pending) |
| P4 | Composite index `(org_id, last_check_in DESC)` | Faster staleness-filtered queries | RHINENG-24465 (Closed) |
| P5 | Move `jsonb_build_object` to Python | Reduce DB CPU on system profile queries | RHINENG-24461 (Closed) |
| P6 | Optimize COUNT(DISTINCT) pagination query | Faster paginated host listing | RHINENG-24460 |
| P7 | Cache staleness config in Redis | Eliminate repeated config lookups | RHINENG-24462 |
| P8 | Eliminate SAP double-query | 50% fewer queries on SAP endpoint | RHINENG-24463 |
| P9 | Evaluate dropping low-usage indexes | Recover ~14.5 GB (per_reporter_staleness GIN, etc.) | RHINENG-24464 |
| P10 | Refactor MQ ingestion to batched queries | Fewer DB round-trips during ingestion | RHINENG-24466 (Code Review) |
| P11 | Deploy OpenTelemetry to staging (Datadog) | Ongoing query/trace visibility | RHINENG-24190 (Code Review) |

> **Speaker notes**: P1 is the headline finding -- a code-only fix that affects every endpoint touching groups. Show the EXPLAIN: 32 partition seq scans because of a missing org_id in the join. Several items are already closed or in development (P3, P4, P5, P10, P11). The table shows we've already delivered wins while identifying the biggest remaining issue.

---

### Slide 13 - Effort vs Impact Matrix

```
                        HIGH IMPACT
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        │  Fix join org_id  │  OTel to staging  │
        │  (P1 - biggest!)  │  Redis caching    │
        │  Drop hosts_old   │  COUNT pagination  │
        │  Drop dead indexes│                   │
        │   QUICK WINS      │    STRATEGIC      │
  LOW ──┼───────────────────┼───────────────────┼── HIGH
 EFFORT │                   │                   │  EFFORT
        │  SAP query fix    │                   │
        │  Low-usage indexes│                   │
        │                   │                   │
        │   INCREMENTAL     │    EVALUATE       │
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                        LOW IMPACT

Already delivered: Composite index (P4), jsonb refactor (P5),
                   Batch MQ queries (P10 - in review)
```

> **Speaker notes**: P1 (fix join org_id) is both low-effort AND high-impact -- it's a code-only fix touching 8 join sites, no migration needed, and it fixes the #1 AAS query in production by enabling partition pruning. This is the clear winner. Quick Wins in the top-left are already in progress (dead indexes, hosts_old). Note the "Already delivered" line at the bottom -- we've already completed several items, which demonstrates momentum.

---

### Slide 14 - Discussion: Where Else Can Tracing Help?

Open discussion prompts for the team:

1. **Export service**: Can we trace export jobs end-to-end? How do we measure export latency per org?

2. **Host reaper**: The reaper processes culled hosts in batches -- tracing could show per-batch performance and identify slow partitions.

3. **Cross-service integration**: Discovery and Swatch consume our Kafka events. Can we propagate trace context in message headers so they can correlate their processing with our ingestion?

4. **SLOs and alerting**: Can we define trace-based SLOs? E.g., "99% of host list requests for orgs with < 10K hosts should complete in < 500ms"

5. **Debugging production issues**: When support escalates a customer complaint, can we search traces by org_id and time range to find exactly what happened?

> **Speaker notes**: This is meant to be interactive. Let the team discuss and capture ideas on a whiteboard or shared doc. These will feed into the afternoon hackathon.

---
---

## Session 3: Operations Hackathon (15:15 - 16:30)

**Goal: See tracing in action, identify gaps, attempt fixes.**

---

### Slide 15 - Hackathon Goals

By the end of this session, we should have:

- [ ] Everyone with tracing running locally
- [ ] Generated realistic traffic and examined real traces
- [ ] Attempted to fix the remaining issues in this epic: RHINENG-24190

**Ground rules:**
- Share interesting findings in Slack / group chat as you go
- We'll do a 10-minute show-and-tell at the end

---

### Slide 16 - Setup Instructions

**Prerequisites:** Docker Desktop, git, local clone of the repo

**Option A: One-command setup (recommended)**

```bash
git checkout <otel-branch-name>
git submodule update --init --recursive
./scripts/demo-tracing.sh
```

This handles everything: builds containers, runs migrations, ingests 100 hosts, and makes API requests. Takes ~3-5 minutes.

**Option B: Manual step-by-step**

```bash
# 1. Switch to the OTel branch
git checkout <otel-branch-name>
git submodule update --init --recursive

# 2. Start all services (including Tempo + Grafana)
docker compose -f dev.yml up -d --build

# 3. Wait for services to be healthy, then run DB migrations
docker exec hbi-web bash -c "FLASK_APP=manage.py flask db upgrade"

# 4. Generate test hosts
NUM_HOSTS=100 docker exec hbi-mq bash -c "NUM_HOSTS=100 python3 utils/kafka_producer.py"

# 5. Open Grafana
open http://localhost:3000
# Navigate to: Explore -> Select "Tempo" datasource
# Search by service name: "host-inventory"
```

**Useful commands:**
- `./scripts/demo-tracing.sh --quick` -- re-seed data without rebuilding
- `./scripts/demo-tracing.sh --clean` -- tear everything down

> **Speaker notes**: Share the branch name with the team before the F2F. Ideally ask everyone to run the script before the hackathon session (e.g., during the Discovery/Swatch discussions) so setup time is minimized.

---

### Slide 17 - Hackathon Tracks

**Track A: Local tracing exploration** (for those new to tracing)

- Exercise 1: Make a `GET /api/hosts` request, find the trace in Tempo, identify SQL queries
- Exercise 2: Find the slowest span in a host list request -- is the bottleneck DB or app logic?
- Exercise 3: Ingest hosts via MQ (`NUM_HOSTS=5`), find the batch trace, check per-message timing
- Exercise 4: Pick the slowest SQL span, run `EXPLAIN (ANALYZE, BUFFERS)` locally
- Bonus: Add a custom span to a code path you're curious about:

```python
from app.telemetry import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my_operation", attributes={"key": "value"}):
    # your code here
    pass
```

---

### Slide 18 - Wrap-up & Action Items

**What we found today:**

| Finding | Impact | Next Step |
|---------|--------|-----------|
| 1. _________________ | ________ | _________________ |
| 2. _________________ | ________ | _________________ |
| 3. _________________ | ________ | _________________ |

**Standing action items:**

- [ ] Deploy OTel instrumentation to staging (JIRA Epic Task 12)
- [ ] Enable `pg_stat_statements` on production (request to DBA team)
- [ ] _(Add items from today's hackathon findings)_

---
---

## Appendix: Key Data Points (Sanitized Reference)

Use these numbers throughout the presentation. All data validated against production.

| Metric | Value | Source |
|--------|-------|--------|
| Total hosts | ~5M | Production DB |
| DB instance type | `db.m7g.8xlarge` (32 vCPU, 128 GB) | AWS RDS |
| Partition count | 32 (HASH on org_id) | Schema |
| `hosts_old` table size | ~361 GB | `pg_total_relation_size` |
| Zero-scan index waste | ~1.3 GB | `pg_stat_user_indexes` |
| Highest AAS query | Group listing: scans all 32 `hosts_groups` partitions (~2.7M rows) due to missing `org_id` in join | RDS Performance Insights |
| Single partition heap size | 8.9 GB (`hosts_p4`) | `pg_total_relation_size` |
| Partition pruning miss | Joins scan 32/32 partitions instead of 1/32 (missing `org_id` in join condition) | `EXPLAIN` plan |
| Affected join sites | 8 code locations across 6 files | Code audit |

---

## Appendix: Preparation Checklist

- [ ] Capture Grafana/Tempo screenshots from local OTel branch for Slides 9 and 16
- [ ] Test the hackathon setup end-to-end on a clean machine
- [ ] Pre-generate the `x-rh-identity` header for demo/hackathon use
- [ ] Have the JIRA Epic link ready to share with the team
- [ ] Coordinate with Asa on Session 1 slide ownership
- [ ] Prepare a shared doc for capturing hackathon findings in real time
