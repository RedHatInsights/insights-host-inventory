# OpenTelemetry Integration Plan for Host Based Inventory (HBI)

> **Learning Day Document** — February 2026
>
> This document serves as both a learning guide to OpenTelemetry and a concrete
> implementation plan for adding distributed tracing, SQL query visibility, and
> request-level observability to the HBI service.

---

## Table of Contents

1. [Why OpenTelemetry?](#1-why-opentelemetry)
2. [Core Concepts (Quick Primer)](#2-core-concepts-quick-primer)
3. [Current Observability State of HBI](#3-current-observability-state-of-hbi)
4. [What We Gain](#4-what-we-gain)
5. [Architecture Overview](#5-architecture-overview)
6. [Implementation Plan](#6-implementation-plan)
   - Phase 1: Foundation & Flask Tracing
   - Phase 2: SQLAlchemy Query Tracing
   - Phase 3: Kafka Distributed Tracing
   - Phase 4: Custom Spans & Business Logic
7. [Package Dependencies](#7-package-dependencies)
8. [Code Examples (HBI-Specific)](#8-code-examples-hbi-specific)
9. [Gunicorn Multi-Worker Considerations](#9-gunicorn-multi-worker-considerations)
10. [Backend & Visualization Options](#10-backend--visualization-options)
11. [Integration with Existing Prometheus Metrics](#11-integration-with-existing-prometheus-metrics)
12. [Configuration & Environment Variables](#12-configuration--environment-variables)
13. [Risks & Considerations](#13-risks--considerations)
14. [Effort Estimates](#14-effort-estimates)
15. [Further Reading](#15-further-reading)

---

## 1. Why OpenTelemetry?

Today, diagnosing performance issues in HBI is difficult:

| Problem | Current State | With OpenTelemetry |
|---------|--------------|-------------------|
| **Slow SQL queries** | We set `statement_timeout` but can't easily identify _which_ queries are slow or correlate them to API requests | Every SQL query becomes a span with duration, statement text, and parent request context |
| **Slow API endpoints** | Prometheus histograms give aggregate latency, but not per-request breakdowns | Each request is a trace with spans for every sub-operation (DB, RBAC calls, Kafka produce) |
| **Cross-service tracing** | `x-rh-insights-request-id` is logged but has no causal linking across services | Trace context propagates through HTTP headers _and_ Kafka message headers automatically |
| **Root cause analysis** | Requires correlating logs across multiple services manually | A single trace shows the full request lifecycle: API → DB → Kafka → downstream consumer |
| **Query-level correlation** | No way to link a slow query back to the API call that triggered it | SQLCommenter injects `traceparent` into SQL comments — visible even in `pg_stat_activity` |

OpenTelemetry is the **CNCF standard** for observability. It's vendor-neutral, widely adopted, and has mature Python instrumentation libraries for every component we use.

---

## 2. Core Concepts (Quick Primer)

### The Three Pillars

```
┌─────────────────────────────────────────────────┐
│              OpenTelemetry Signals               │
├───────────────┬───────────────┬─────────────────┤
│    Traces     │    Metrics    │      Logs       │
│  (request     │  (counters,   │  (structured    │
│   flow)       │   histograms) │   events)       │
└───────────────┴───────────────┴─────────────────┘
```

### Key Terms

- **Trace**: The complete journey of a request through the system. Has a unique `trace_id`.
- **Span**: A single unit of work within a trace (e.g., one SQL query, one HTTP call). Has a `span_id`, a parent `span_id`, start/end timestamps, attributes, and status.
- **Context Propagation**: How trace identity passes between services — typically via HTTP headers (`traceparent`) or Kafka message headers.
- **Exporter**: Sends telemetry data to a backend (Grafana Tempo, OTLP collector, etc.).
- **Instrumentor**: Library that automatically creates spans for a framework (Flask, SQLAlchemy, etc.).
- **Span Attributes**: Key-value metadata on a span (e.g., `http.method=GET`, `db.statement=SELECT ...`).
- **SQLCommenter**: Injects trace context as SQL comments so DBAs can correlate queries to traces.

### Anatomy of a Trace

```
Trace: abc123
│
├── Span: GET /api/inventory/v1/hosts (Flask)         [0ms ─────── 250ms]
│   ├── Span: RBAC permission check (HTTP)            [5ms ── 45ms]
│   ├── Span: SELECT hosts (SQLAlchemy)               [50ms ──── 180ms]
│   │   └── /* traceparent='00-abc123-...' */ SELECT * FROM hosts WHERE ...
│   └── Span: Kafka produce: platform.inventory.events [185ms ─ 210ms]
│
└── (downstream consumer picks up trace from Kafka headers)
    └── Span: process host event (MQ Service)         [215ms ──── 400ms]
        ├── Span: INSERT host (SQLAlchemy)             [220ms ── 350ms]
        └── Span: Kafka produce: notification          [355ms ─ 380ms]
```

---

## 3. Current Observability State of HBI

### What we have

| Component | Tool | What it gives us |
|-----------|------|-----------------|
| **Metrics** | `prometheus-client` + `prometheus-flask-exporter` | Aggregate request latency histograms, counters for host CRUD, Kafka message counts |
| **Logging** | `logstash-formatter` + `watchtower` | Structured JSON logs with `request_id`, `org_id`, `account_number` |
| **Health** | `/health`, `/metrics`, `/version` endpoints | Liveness, Prometheus scrape, build info |
| **Request ID** | `x-rh-insights-request-id` header | Basic request correlation in logs |

### What we're missing

- **Distributed traces** linking API → DB → Kafka → downstream
- **Per-request SQL query visibility** (which queries, how long, which request triggered them)
- **Automatic span creation** for HTTP handlers, DB operations, outbound HTTP calls
- **Cross-service context propagation** through Kafka messages
- **Trace-to-log correlation** (linking a trace_id to structured log entries)

---

## 4. What We Gain

### Scenario 1: "Why is GET /hosts slow for this org?"

**Today**: Check Prometheus p99, grep logs for the org_id, guess which query is slow.

**With OpenTelemetry**: Filter traces by `org_id` attribute, see the exact trace with spans showing:
- Flask request span: 2.3s total
- RBAC check span: 120ms
- SQLAlchemy span: 2.1s — `SELECT * FROM hosts WHERE org_id = '...' LIMIT 50 OFFSET 4000` ← the culprit

### Scenario 2: "The MQ service is falling behind on ingress"

**Today**: Check Kafka lag metrics, guess which step is slow.

**With OpenTelemetry**: Trace follows the message from API → Kafka → MQ consumer, showing that `add_host()` takes 800ms because of a lock contention in the `INSERT ... ON CONFLICT` path.

### Scenario 3: "Which queries are responsible for DB load?"

**Today**: Check `pg_stat_statements`, but can't link queries to application context.

**With OpenTelemetry + SQLCommenter**: Every query has a SQL comment like:
```sql
/* traceparent='00-abc123-def456-01',route='/api/inventory/v1/hosts' */ SELECT ...
```
Now DBAs can correlate slow queries in PostgreSQL directly to application traces.

---

## 5. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      HBI Services                            │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐     │
│  │ Web API  │  │  MQ Service  │  │  Export Service     │     │
│  │ (Flask + │  │  (Kafka      │  │  (Kafka consumer)   │     │
│  │ Gunicorn)│  │  consumer)   │  │                     │     │
│  └────┬─────┘  └──────┬───────┘  └─────────┬──────────┘     │
│       │               │                    │                 │
│       └───────────┬───┴────────────────────┘                 │
│                   │                                          │
│         ┌─────────▼──────────┐                               │
│         │  OTel SDK          │                               │
│         │  - TracerProvider  │                               │
│         │  - SpanProcessors  │                               │
│         │  - Instrumentors   │                               │
│         └─────────┬──────────┘                               │
│                   │  OTLP (gRPC or HTTP)                     │
└───────────────────┼──────────────────────────────────────────┘
                    │
          ┌─────────▼──────────┐
          │  OTel Collector    │   (optional, recommended in prod)
          │  - Receives OTLP   │
          │  - Processes/samples│
          │  - Exports          │
          └─────────┬──────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
   ┌────▼────────┐ │     ┌─────▼───────┐
   │ Grafana     │ │     │ Prometheus  │
   │ Tempo       │ │     │ (metrics)   │
   │ (traces)    │ │     └─────────────┘
   └─────────────┘ │
                    │
              ┌─────▼─────┐
              │  Grafana   │  ← unified UI for metrics + traces + logs
              │  Dashboard │
              └────────────┘
```

---

## 6. Implementation Plan

### Phase 1: Foundation & Flask Tracing

**Goal**: Get basic request tracing working for the Web API.

**Steps**:

1. **Add core OTel packages** to `Pipfile` (see [Section 7](#7-package-dependencies))

2. **Create `app/telemetry.py`** — centralized OTel initialization module:
   - Configure `TracerProvider` with `Resource` attributes (`service.name`, `service.version`)
   - Set up `BatchSpanProcessor` with OTLP exporter
   - Configure `FlaskInstrumentor`
   - Add conditional enable/disable via `OTEL_ENABLED` environment variable

3. **Instrument Flask** in `app/__init__.py`:
   - Call `FlaskInstrumentor().instrument_app(flask_app)` after app creation
   - Exclude health/metrics endpoints via `OTEL_PYTHON_FLASK_EXCLUDED_URLS`
   - Add custom span attributes for `org_id` and `request_id` via request hooks

4. **Instrument outbound HTTP** (RBAC calls):
   - Add `opentelemetry-instrumentation-requests` or `opentelemetry-instrumentation-urllib3`
   - Automatically traces RBAC permission checks

5. **Handle Gunicorn** (see [Section 9](#9-gunicorn-multi-worker-considerations)):
   - Add `post_fork` hook to `gunicorn.conf.py`
   - Initialize `TracerProvider` per worker process

6. **Add to `dev.yml`**:
   - Add Grafana Tempo + Grafana containers for local development
   - Set OTLP endpoint env vars

**Deliverable**: Every API request produces a trace visible in Grafana (Tempo), showing request duration, HTTP method, path, status code, org_id.

**Estimated effort**: 2-3 days

---

### Phase 2: SQLAlchemy Query Tracing

**Goal**: Every SQL query is a child span of the request that triggered it, with query text and duration.

**Steps**:

1. **Add `opentelemetry-instrumentation-sqlalchemy`** to `Pipfile`

2. **Instrument SQLAlchemy** in `app/telemetry.py`:
   - Use `SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=True)`
   - Enable SQLCommenter for trace context in SQL queries

3. **Handle Flask-SQLAlchemy**:
   - Access the engine from `db.engine` after app initialization
   - Instrument in the app factory after `db.init_app(flask_app)`

4. **Instrument standalone engines** in jobs:
   - Jobs like `host_reaper`, `pendo_syncher`, `rebuild_events_topic` create engines directly
   - Pass each engine to `SQLAlchemyInstrumentor().instrument(engine=engine)`

5. **Configure span attributes**:
   - `db.system = "postgresql"`
   - `db.name` from connection string
   - `db.statement` contains the SQL text (consider sanitization for PII)

**Deliverable**: API request traces now show nested SQL query spans. DBAs see `traceparent` in `pg_stat_activity`.

**Example trace**:
```
GET /api/inventory/v1/hosts                    [0ms ─── 180ms]
  ├── SELECT count(*) FROM hosts WHERE ...     [12ms ── 45ms]
  └── SELECT * FROM hosts WHERE ... LIMIT 50   [50ms ── 170ms]
```

**Estimated effort**: 1-2 days

---

### Phase 3: Kafka Distributed Tracing

**Goal**: Traces propagate across Kafka — from API/producer through to MQ service/consumer.

**Steps**:

1. **Add `opentelemetry-instrumentation-confluent-kafka`** to `Pipfile`

2. **Instrument the Kafka producer** in `app/queue/event_producer.py`:
   - Use `ConfluentKafkaInstrumentor().instrument()` for automatic instrumentation, OR
   - Manually inject trace context into Kafka message headers using `TraceContextTextMapPropagator`

3. **Instrument the Kafka consumer** in `inv_mq_service.py`:
   - Extract trace context from incoming message headers
   - Create consumer spans as children of the producer trace

4. **Handle the Export Service** similarly in `inv_export_service.py`

5. **Verify end-to-end trace propagation**:
   - POST to create a host → Kafka produce → MQ service consume → DB insert
   - All visible as a single trace in Grafana/Tempo

**Deliverable**: Full distributed traces from API → Kafka → consumer → DB.

**Estimated effort**: 2-3 days

---

### Phase 4: Custom Spans & Business Logic

**Goal**: Add meaningful custom spans for key business operations.

**Steps**:

1. **Add custom spans** for critical operations:
   ```python
   from opentelemetry import trace

   tracer = trace.get_tracer(__name__)

   def add_host(host_data, ...):
       with tracer.start_as_current_span("add_host") as span:
           span.set_attribute("host.reporter", host_data.reporter)
           span.set_attribute("host.org_id", host_data.org_id)
           # ... existing logic
   ```

2. **Instrument key paths**:
   - `lib/host_repository.py` — host CRUD operations, deduplication
   - `lib/host_delete.py` — host deletion with event production
   - `lib/group_repository.py` — group operations
   - `app/queue/host_mq.py` — message handling pipeline
   - `api/host.py` — API handler logic

3. **Add span events** for important milestones:
   ```python
   span.add_event("host_deduplicated", {"match_count": len(matches)})
   span.add_event("staleness_check_complete", {"is_stale": is_stale})
   ```

4. **Record errors** properly:
   ```python
   except Exception as e:
       span.set_status(StatusCode.ERROR, str(e))
       span.record_exception(e)
       raise
   ```

5. **Add trace-to-log correlation**:
   - Include `trace_id` and `span_id` in log records via the `ContextualFilter`
   - Enables searching logs by trace ID

**Estimated effort**: 3-5 days (ongoing, iterative)

---

## 7. Package Dependencies

Add these to `Pipfile` under `[packages]`:

```toml
# OpenTelemetry Core
opentelemetry-api = "~=1.32"
opentelemetry-sdk = "~=1.32"

# OTLP Exporter (choose one or both)
opentelemetry-exporter-otlp-proto-http = "~=1.32"
# opentelemetry-exporter-otlp-proto-grpc = "~=1.32"   # alternative: gRPC

# Auto-Instrumentation Libraries
opentelemetry-instrumentation-flask = "~=0.60b"
opentelemetry-instrumentation-sqlalchemy = "~=0.60b"
opentelemetry-instrumentation-confluent-kafka = "~=0.60b"
opentelemetry-instrumentation-requests = "~=0.60b"     # for outbound HTTP (RBAC)
opentelemetry-instrumentation-urllib3 = "~=0.60b"      # alternative to requests

# Optional but recommended
opentelemetry-instrumentation-logging = "~=0.60b"      # trace-log correlation
opentelemetry-instrumentation-redis = "~=0.60b"        # Redis cache tracing
```

> **Note**: Check [PyPI](https://pypi.org/project/opentelemetry-api/) for the latest
> stable versions at the time of implementation.

---

## 8. Code Examples (HBI-Specific)

### 8.1 Telemetry Initialization Module

Create `app/telemetry.py`:

```python
"""OpenTelemetry initialization for HBI services."""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from app.logging import get_logger

logger = get_logger(__name__)

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"


def init_otel(service_name: str, service_version: str = "unknown"):
    """Initialize OpenTelemetry tracing. Call once per process."""
    if not OTEL_ENABLED:
        logger.info("OpenTelemetry is disabled (OTEL_ENABLED != 'true')")
        return

    resource = Resource.create(attributes={
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": os.getenv("CLOWDER_ENABLED", "false"),
    })

    provider = TracerProvider(resource=resource)

    # OTLP exporter — endpoint configured via OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry initialized for service=%s", service_name)


def instrument_flask_app(flask_app):
    """Instrument a Flask/Connexion app with OpenTelemetry."""
    if not OTEL_ENABLED:
        return

    FlaskInstrumentor().instrument_app(
        flask_app,
        excluded_urls="health,metrics,version",  # skip noisy endpoints
        request_hook=_request_hook,
        response_hook=_response_hook,
    )
    logger.info("Flask instrumented with OpenTelemetry")


def instrument_sqlalchemy(engine):
    """Instrument a SQLAlchemy engine with OpenTelemetry."""
    if not OTEL_ENABLED:
        return

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=True,  # adds traceparent to SQL comments
        commenter_options={
            "db_framework": True,
            "db_driver": True,
        },
    )
    logger.info("SQLAlchemy engine instrumented with OpenTelemetry")


def instrument_outbound_http():
    """Instrument outbound HTTP calls (e.g., RBAC) with OpenTelemetry."""
    if not OTEL_ENABLED:
        return

    RequestsInstrumentor().instrument()
    logger.info("Outbound HTTP instrumented with OpenTelemetry")


def _request_hook(span, environ):
    """Add HBI-specific attributes to every request span.

    This ensures that org_id and request_id are searchable in Grafana/Tempo,
    so you can filter traces like:
        - resource.hbi.org_id = "12345"       → all traces for an org
        - resource.hbi.request_id = "abc-..."  → find a specific request
    """
    if span and span.is_recording():
        # 1. Add request_id from the x-rh-insights-request-id header
        from flask import request
        request_id = request.headers.get("x-rh-insights-request-id", "")
        if request_id:
            span.set_attribute("hbi.request_id", request_id)

        # 2. Add org_id from the decoded identity header
        from app.auth.identity import get_current_identity
        try:
            identity = get_current_identity()
            if identity:
                span.set_attribute("hbi.org_id", identity.org_id or "")
        except Exception:
            pass  # Don't break requests if identity extraction fails


def _response_hook(span, status, response_headers):
    """Add response-level attributes to request spans."""
    if span and span.is_recording():
        span.set_attribute("http.status_code", status)
```

### 8.2 Integration in `app/__init__.py`

```python
# Near the end of create_app(), after db.init_app():
from app.telemetry import init_otel, instrument_flask_app, instrument_sqlalchemy, instrument_outbound_http

def create_app(runtime_environment):
    # ... existing app creation code ...

    # Initialize OpenTelemetry (Phase 1)
    init_otel(
        service_name="host-inventory",
        service_version=get_build_version(),
    )

    # Instrument Flask (Phase 1)
    instrument_flask_app(flask_app)

    # Instrument SQLAlchemy (Phase 2)
    instrument_sqlalchemy(db.engine)

    # Instrument outbound HTTP for RBAC calls (Phase 1)
    instrument_outbound_http()

    return application
```

### 8.3 Gunicorn Configuration

```python
# gunicorn.conf.py — add post_fork hook for OTel
from app.telemetry import init_otel

def post_fork(server, worker):
    """Initialize OTel per worker process (BatchSpanProcessor is not fork-safe)."""
    init_otel(
        service_name="host-inventory",
    )
```

### 8.4 Trace-Log Correlation

Update `app/logging.py` `ContextualFilter`:

```python
from opentelemetry import trace

class ContextualFilter(logging.Filter):
    def filter(self, log_record):
        # ... existing request_id, org_id logic ...

        # Add trace context to every log line
        span = trace.get_current_span()
        if span and span.get_span_context().trace_id:
            ctx = span.get_span_context()
            log_record.trace_id = format(ctx.trace_id, "032x")
            log_record.span_id = format(ctx.span_id, "016x")
        else:
            log_record.trace_id = "0" * 32
            log_record.span_id = "0" * 16

        return True
```

Now logs can be searched by `trace_id`, linking them directly to traces in Grafana Tempo.

### 8.5 Custom Span for Business Logic

```python
# lib/host_repository.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def add_host(host_data, staleness_timestamps, fields):
    with tracer.start_as_current_span("hbi.add_host") as span:
        span.set_attribute("hbi.host.reporter", host_data.get("reporter", "unknown"))
        span.set_attribute("hbi.host.org_id", host_data.get("org_id", ""))

        # ... existing dedup + insert logic ...

        span.add_event("host_created", {"host_id": str(new_host.id)})
        return new_host
```

---

## 9. Gunicorn Multi-Worker Considerations

This is a **critical detail** for HBI since the web service runs under Gunicorn.

### The Problem

Gunicorn uses a **pre-fork** model. The `BatchSpanProcessor` uses threads and locks internally. When Gunicorn forks workers, the child processes inherit these locks in an inconsistent state, causing **deadlocks**.

### The Solution

Initialize OTel **after** the fork, in each worker process, using Gunicorn's `post_fork` hook:

```python
# gunicorn.conf.py
def post_fork(server, worker):
    from app.telemetry import init_otel
    init_otel(service_name="host-inventory")
```

**Important**: Do NOT call `init_otel()` at module import time or in the master process. Only call it in:
- `post_fork` for Gunicorn workers
- `main()` for the MQ service and Export service (they don't use fork)

### Compatibility with Existing Prometheus Setup

The existing `when_ready` and `child_exit` hooks for Prometheus metrics are **unaffected**. OTel tracing and Prometheus metrics coexist cleanly — they serve different purposes.

---

## 10. Backend & Visualization — Grafana Tempo

Since we already use **Prometheus + Grafana**, the natural tracing backend is
**Grafana Tempo**. Tempo stores traces, and Grafana provides the UI to search
and visualize them — all in the same dashboards where we already view metrics.

### Why Grafana Tempo?

| Aspect | Benefit |
|--------|---------|
| **Unified UI** | Traces, metrics, and logs all in Grafana — no extra tool to learn |
| **Metrics → Traces** | Click from a Prometheus metric spike directly into the traces that caused it (Exemplars) |
| **Logs → Traces** | Click a `trace_id` in a log line to jump to the full trace |
| **Cost-effective** | Tempo uses object storage (S3/GCS), no indexing — much cheaper than Elasticsearch-backed alternatives |
| **OTLP native** | Accepts OTLP directly — no translation layer needed |
| **Already in our stack** | No new vendor, no new UI to learn, integrates with existing Grafana dashboards |

### For Local Development

Add **Grafana Tempo** and **Grafana** to `dev.yml`:

```yaml
# Add to dev.yml
services:
  tempo:
    image: grafana/tempo:2.7.1
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./dev/tempo.yaml:/etc/tempo.yaml
    ports:
      - "4318:4318"     # OTLP HTTP receiver
      - "3200:3200"     # Tempo query API

  grafana:
    image: grafana/grafana:11.5.2
    ports:
      - "3000:3000"     # Grafana UI
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: "Admin"
    volumes:
      - ./dev/grafana-datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml
```

Create `dev/tempo.yaml` (minimal config):

```yaml
# dev/tempo.yaml
stream_over_http_enabled: true
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        http:
          endpoint: "0.0.0.0:4318"

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks

metrics_generator:
  registry:
    external_labels:
      source: tempo
  storage:
    path: /tmp/tempo/generator/wal
    remote_write:
      - url: http://prometheus:9090/api/v1/write
        send_exemplars: true
```

Create `dev/grafana-datasources.yaml`:

```yaml
# dev/grafana-datasources.yaml
apiVersion: 1
datasources:
  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    isDefault: true
    jsonData:
      tracesToMetrics:
        datasourceUid: prometheus
      serviceMap:
        datasourceUid: prometheus
      nodeGraph:
        enabled: true
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
```

Access Grafana at `http://localhost:3000` → **Explore** → select **Tempo** data source.

### The Grafana Workflow (Metrics → Traces → Logs)

This is the real power of using Tempo with your existing Prometheus + Grafana:

```
 1. Grafana Dashboard                    2. Trace View (Tempo)
┌──────────────────────────┐         ┌──────────────────────────────┐
│ GET /hosts p99 latency   │         │ Trace: abc123                │
│ ████████████████ 2.3s ▲  │ ──────► │ ├── GET /hosts      [2.3s]  │
│         click spike      │         │ │  ├── RBAC check   [0.1s]  │
│                          │         │ │  ├── SELECT hosts  [2.1s] ◄── the culprit!
└──────────────────────────┘         │ │  └── Kafka produce [0.05s]│
                                     └──────────────────────────────┘
                                                    │
                                                    ▼
                                      3. Logs (filtered by trace_id)
                                     ┌──────────────────────────────┐
                                     │ trace_id=abc123              │
                                     │ "Slow query detected for     │
                                     │  org_id=12345..."            │
                                     └──────────────────────────────┘
```

### Prometheus Exemplars (Metrics → Traces Link)

To enable clicking from a Prometheus metric directly into a trace, you can expose
**exemplars** from OTel. This is an optional future enhancement where a histogram
bucket includes a sample `trace_id`, so Grafana can link to Tempo.

### For Production (Clowder)

Use the **OpenTelemetry Collector** as a middle layer between HBI and Tempo:

```
HBI Services ──OTLP──► OTel Collector ──OTLP──► Grafana Tempo ──► Grafana UI
                              │
                              └──► (optional) Prometheus remote-write for span metrics
```

The Collector lets you:
- **Sample traces** (e.g., keep 10% of healthy traces, 100% of errors)
- **Process spans** (attribute enrichment, PII redaction)
- **Buffer and retry** on export failures
- **Change backends** without touching application code

---

## 11. Integration with Existing Prometheus Metrics

OpenTelemetry **does not replace** the existing Prometheus metrics. They complement each other:

| Signal | Tool | Use Case |
|--------|------|----------|
| **Metrics** | Prometheus (existing) | Aggregate dashboards, alerting, SLOs |
| **Traces** | OpenTelemetry (new) | Per-request debugging, latency breakdown, distributed tracing |
| **Logs** | Logstash/CloudWatch (existing) | Debugging with trace_id correlation (new) |

### The RED Method + Traces

Continue using Prometheus for **R**ate, **E**rrors, **D**uration at the aggregate level. Use traces to **drill down** when an anomaly is detected:

1. Prometheus alert fires: "p99 latency > 2s on GET /hosts"
2. Click the spike in Grafana → linked Exemplar opens the trace in Tempo
3. Or go to Grafana Explore → Tempo, filter by: `service=host-inventory`, `http.target=/api/inventory/v1/hosts`, `duration > 2s`
4. See the exact trace: 1.8s in a single SQL query with a missing index

### Optional: OTel Metrics (Future)

OpenTelemetry can also generate metrics (via `opentelemetry-sdk` `MeterProvider`), and even export them in Prometheus format. This could eventually **unify** metrics + traces under one SDK. But this is a _future_ consideration — start with traces only.

---

## 12. Configuration & Environment Variables

### Core OTel Configuration

```bash
# Enable/disable (our custom flag)
OTEL_ENABLED=true

# Service identification
OTEL_SERVICE_NAME=host-inventory
OTEL_RESOURCE_ATTRIBUTES=service.version=1.0.0,deployment.environment=stage

# OTLP Exporter
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_COMPRESSION=gzip

# Sampling (reduce volume in production)
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1  # Sample 10% of traces

# Flask-specific
OTEL_PYTHON_FLASK_EXCLUDED_URLS=health,metrics,version
```

### Clowder Integration

In `deploy/clowdapp.yml`, add environment variables to the pod spec:

```yaml
env:
  - name: OTEL_ENABLED
    value: "true"
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-collector.observability.svc:4318"
  - name: OTEL_TRACES_SAMPLER
    value: "parentbased_traceidratio"
  - name: OTEL_TRACES_SAMPLER_ARG
    value: "0.1"
```

---

## 13. Risks & Considerations

### Performance Impact

- **Flask instrumentation**: Negligible (<1ms per request overhead)
- **SQLAlchemy instrumentation**: Negligible (event hooks are lightweight)
- **Kafka instrumentation**: Minimal (header injection/extraction)
- **BatchSpanProcessor**: Batches spans in memory, exports asynchronously — minimal latency impact
- **Sampling**: Use `parentbased_traceidratio` in production to control volume

### Security / PII Considerations

- **SQL statements**: OTel captures query text by default. Ensure parameterized queries don't leak sensitive data. Consider using `db.statement` sanitization if needed.
- **HTTP headers**: Avoid capturing sensitive headers (e.g., `x-rh-identity`). Configure `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS`.
- **Span attributes**: Don't add PII (email, names) to span attributes.

### Dependency Management

- OTel Python libraries follow a `1.x` (stable API/SDK) and `0.x` (instrumentation) versioning scheme. Instrumentation packages are still in beta but widely used in production.
- Pin versions in `Pipfile` to avoid breaking changes.

### Rollback Plan

- The `OTEL_ENABLED=false` flag makes it trivial to disable. No code changes needed.
- Even if OTel is enabled, if the exporter endpoint is unreachable, spans are silently dropped — **no impact on service availability**.

---

## 14. Effort Estimates

| Phase | Scope | Effort | Risk |
|-------|-------|--------|------|
| **Phase 1**: Flask + Foundation | `app/telemetry.py`, `app/__init__.py`, `gunicorn.conf.py`, `dev.yml` | 2-3 days | Low |
| **Phase 2**: SQLAlchemy | Add instrumentor, verify traces in Grafana/Tempo | 1-2 days | Low |
| **Phase 3**: Kafka | Producer + consumer instrumentation, end-to-end trace verification | 2-3 days | Medium (context propagation edge cases) |
| **Phase 4**: Custom spans + polish | Business logic spans, trace-log correlation, documentation | 3-5 days | Low |
| **Production deployment** | Clowder config, OTel Collector setup, sampling tuning | 2-3 days | Medium (infrastructure) |
| **Total** | | **10-16 days** | |

Phases 1 and 2 can be shipped together as a first PR. Phase 3 can follow shortly after. Phase 4 is ongoing as the team identifies valuable instrumentation points.

---

## 15. Further Reading

### Official Documentation
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry Flask Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html)
- [OpenTelemetry SQLAlchemy Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html)
- [Working with Fork Process Models (Gunicorn)](https://opentelemetry-python.readthedocs.io/en/stable/examples/fork-process-model/README.html)

### Tutorials & Guides
- [OpenTelemetry Python Getting Started](https://opentelemetry.io/docs/languages/python/getting-started/)
- [SQLCommenter for Query-Level Trace Correlation](https://oneuptime.com/blog/post/2026-02-06-sqlcommenter-opentelemetry-sqlalchemy-trace-correlation/view)

### Backends (Grafana Stack)
- [Grafana Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [Grafana Tempo Getting Started](https://grafana.com/docs/tempo/latest/getting-started/)
- [Grafana Explore Traces](https://grafana.com/docs/grafana/latest/explore/simplified-exploration/traces/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Prometheus Exemplars](https://prometheus.io/docs/prometheus/latest/feature_flags/#exemplars-storage)

### Concepts
- [OpenTelemetry Concepts](https://opentelemetry.io/docs/concepts/)
- [W3C Trace Context Specification](https://www.w3.org/TR/trace-context/)

---

## Appendix: Quick-Start Checklist

For a **hands-on learning session today**, here's the minimal path to see traces:

- [ ] Add OTel packages to Pipfile and `pipenv install --dev`
- [ ] Create `app/telemetry.py` (copy from Section 8.1)
- [ ] Add `instrument_flask_app()` call in `app/__init__.py`
- [ ] Add Grafana Tempo + Grafana to `dev.yml` (copy from Section 10)
- [ ] Create `dev/tempo.yaml` and `dev/grafana-datasources.yaml` (copy from Section 10)
- [ ] Set `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`
- [ ] Start services: `docker compose -f dev.yml up -d`
- [ ] Make a few API requests
- [ ] Open `http://localhost:3000` → Explore → Tempo and explore your first traces!
