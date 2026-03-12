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

### Slide 7 - What is Distributed Tracing?

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

### Slide 8 - OpenTelemetry: The Standard

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

### Slide 9 - What We Built on the Day of Learning

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

### Slide 10 - Live Demo: Traces in Grafana Tempo

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

### Slide 11 - Gaps Tracing Closes

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

### Slide 12 - What We Found Using Traces + DB Analysis

The Day of Learning tracing work led us to investigate production query patterns. Here's what we confirmed:

**Sequential scans instead of index scans:**
- The highest-cost query (`hosts_groups` count) does 2 full sequential scans
- The planner chose this because partition statistics were never collected

**Statistics gap:**
- `ANALYZE` has never been triggered on host partitions
- The planner estimated 25M join rows for a result set of ~31K
- This caused it to choose hash join + seq scan instead of nested loop + index scan

**Dead weight consuming resources:**
- `hosts_old` table: ~361 GB, never queried
- Zero-scan indexes: ~1.3 GB (GIN on groups, GIN on workloads, redundant org_id)
- These consume buffer cache space, competing with active data

**Query patterns that could be optimized:**
- `jsonb_build_object` assembling system profile JSON in PostgreSQL instead of Python
- SAP aggregation endpoint executing two queries when one would suffice
- Staleness configuration fetched from DB on every request (could be cached)

> **Speaker notes**: The key narrative is: tracing gave us the visibility to ask the right questions, and production validation gave us the evidence to prioritize. Without tracing, these issues would have stayed hidden in aggregate metrics.

---

### Slide 13 - Proposed Optimizations

| Priority | Optimization | Estimated Impact | Status |
|----------|-------------|-----------------|--------|
| P1 | Run `ANALYZE` on all partitions | Correct planner estimates immediately, fix highest-AAS query plan | **New ticket** |
| P2 | Covering index `(org_id, id, deletion_timestamp)` | Fix highest-AAS query: eliminate seq scans on hosts | **New ticket** |
| P3 | Drop `hosts_old` table | ~361 GB freed, reduced backup time | RHINENG-24456 |
| P4 | Drop zero-scan indexes | ~1.3 GB freed, less buffer cache waste | RHINENG-24458 (Release Pending) |
| P5 | Composite index `(org_id, last_check_in DESC)` | Faster staleness-filtered queries | RHINENG-24465 (Closed) |
| P6 | Move `jsonb_build_object` to Python | Reduce DB CPU on system profile queries | RHINENG-24461 (Closed) |
| P7 | Optimize COUNT(DISTINCT) pagination query | Faster paginated host listing | RHINENG-24460 |
| P8 | Cache staleness config in Redis | Eliminate repeated config lookups | RHINENG-24462 |
| P9 | Eliminate SAP double-query | 50% fewer queries on SAP endpoint | RHINENG-24463 |
| P10 | Evaluate dropping low-usage indexes | Recover ~14.5 GB (per_reporter_staleness GIN, etc.) | RHINENG-24464 |
| P11 | Refactor MQ ingestion to batched queries | Fewer DB round-trips during ingestion | RHINENG-24466 (Code Review) |
| P12 | Deploy OpenTelemetry to staging | Ongoing query/trace visibility | RHINENG-24190 (Code Review) |

> **Speaker notes**: Walk through each one briefly. P1 and P2 are the newest findings -- together they fix the highest-cost query in production. P1 is a zero-code-change DBA action. Several items are already in development (P4, P5, P6, P11, P12). The table shows a healthy mix of quick wins, in-progress work, and strategic items.

---

### Slide 14 - Effort vs Impact Matrix

```
                        HIGH IMPACT
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        │  Run ANALYZE (P1) │  OTel to staging  │
        │  Drop hosts_old   │  Covering index   │
        │  Drop dead indexes│  Redis caching    │
        │                   │  COUNT pagination  │
        │   QUICK WINS      │    STRATEGIC      │
  LOW ──┼───────────────────┼───────────────────┼── HIGH
 EFFORT │                   │                   │  EFFORT
        │  SAP query fix    │  jsonb refactor   │
        │  Low-usage indexes│  Batch MQ queries │
        │                   │                   │
        │   INCREMENTAL     │    EVALUATE       │
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                        LOW IMPACT
```

> **Speaker notes**: Start from the top-left (Quick Wins). P1 (Run ANALYZE) is the single highest-impact item and requires zero code changes -- just a DBA action. Several Quick Wins are already done or in release (dead indexes, composite index). The Covering Index (P2) is Strategic because it requires a migration but directly fixes the highest-AAS query. Items already closed (composite index, jsonb refactor) can be mentioned as wins already delivered.

---

### Slide 15 - Discussion: Where Else Can Tracing Help?

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

### Slide 16 - Hackathon Goals

By the end of this session, we should have:

- [ ] Everyone with tracing running locally
- [ ] Generated realistic traffic and examined real traces
- [ ] Identified at least 2-3 performance observations from traces
- [ ] Created tickets or attempted fixes for findings

**Ground rules:**
- Work in pairs or small groups
- Share interesting findings in Slack / group chat as you go
- We'll do a 10-minute show-and-tell at the end

---

### Slide 17 - Setup Instructions

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

### Slide 18 - Hackathon Tracks

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

**Track B: Deploy tracing to staging** (stretch goal)

Goal: Get HBI traces flowing in staging using Sumologic as the trace backend.

```
HBI Pods (web/mq) ──OTLP──> OTel Collector ──OTLP──> Sumologic
```

**Confirmed**: Sumologic tracing is available in our plan (visible under + New -> Traces). The team already has a Sumologic account with OTel support.

**Step 1: Create an OTLP source in Sumologic**
- Go to **Manage Data** -> look for **Collection** or use the **Unified Data Collection with OTel** wizard
- Create an HTTP Source endpoint for OTLP trace ingestion
- This gives you an endpoint URL + authentication token

**Step 2: Choose a deployment approach**

Option A -- Direct export (simplest, good for hackathon):
- Point HBI pods directly at the Sumologic OTLP endpoint
- Set `OTEL_EXPORTER_OTLP_ENDPOINT` in staging `clowdapp.yml` to the Sumologic URL
- Add the auth token via environment variable or secret
- No collector needed, fastest path to traces

Option B -- OTel Collector (recommended for production):
- Deploy an OTel Collector in the staging namespace
- HBI pods send traces to the collector, collector forwards to Sumologic
- Benefits: sampling, batching, retry, decouples app from backend
- Can deploy via Kubernetes Helm chart or standalone OpenShift Deployment

**Step 3: Validate**
- Make requests in staging
- Open Sumologic -> **Observability** -> **Application Monitoring**:
  - **Transaction Traces**: Search and view individual trace waterfalls (like Grafana Tempo)
  - **Services**: See `host-inventory` appear as a service with latency/error metrics
  - **Span Analytics**: Run aggregate queries across spans (e.g., P99 by endpoint, errors by org_id)
- Verify custom attributes are searchable: `hbi.org_id`, `hbi.request_id`

**Questions to answer during the hackathon:**
- Should we use sampling (e.g., 10% of traces) to control data volume in staging/prod?
- Do we need to request OTLP source creation through the Sumologic onboarding YAML config, or can we create it directly in the UI?
- Can Sumologic's tracing UI filter by our custom attributes (`hbi.org_id`, `hbi.request_id`)?

---

### Slide 19 - Wrap-up & Action Items

**What we found today:**

| Finding | Impact | Next Step |
|---------|--------|-----------|
| 1. _________________ | ________ | _________________ |
| 2. _________________ | ________ | _________________ |
| 3. _________________ | ________ | _________________ |

**Standing action items:**

- [ ] Deploy OTel instrumentation to staging (JIRA Epic Task 11)
- [ ] Run `ANALYZE` on production host partitions
- [ ] Merge PR #3719 (drop zero-scan indexes)
- [ ] Merge composite index migration
- [ ] Evaluate covering index for hosts_groups join query
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
| Highest AAS query | hosts_groups count (2 seq scans, hash join) | RDS Performance Insights |
| Planner cardinality error | Estimated 25M rows, actual ~31K | `EXPLAIN` on primary |
| Partition statistics | Never analyzed (autoanalyze not triggered) | `pg_stat_user_tables` |
| Buffer cache | Under pressure from dead weight | Estimated from index/table ratios |

---

## Appendix: Preparation Checklist

- [ ] Capture Grafana/Tempo screenshots from local OTel branch for Slides 10 and 17
- [ ] Test the hackathon setup end-to-end on a clean machine
- [ ] Pre-generate the `x-rh-identity` header for demo/hackathon use
- [ ] Have the JIRA Epic link ready to share with the team
- [ ] Coordinate with Asa on Session 1 slide ownership
- [ ] Prepare a shared doc for capturing hackathon findings in real time
