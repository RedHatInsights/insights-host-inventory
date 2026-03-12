# HBI RDS Instance Downsizing Proposal

## Executive Summary

Analysis of production RDS metrics shows all three HBI database instances (primary writer
and two read replicas) are significantly oversized. HBI's actual application workload
consumes a fraction of provisioned capacity. Additionally, the SWATCH (subscriptions-watch)
team's `InventoryHost.streamFacts` query was the dominant consumer on the primary read
replica, accounting for ~99% of its DB load. A fix has been submitted
([rhsm-subscriptions PR #5846](https://github.com/RedHatInsights/rhsm-subscriptions/pull/5846))
that reduces this query's execution time by ~97% (from ~8s to ~224ms per org), which will
effectively eliminate it as a load concern.

This proposal presents a plan to right-size the infrastructure, with projected savings
of **~75% on read replica costs** and **~50% on the primary writer** — totaling
**~$47K/year**.

---

## Current State

### Instances

| Instance | Type | vCPUs | RAM | Role | Monthly Cost (on-demand) |
|----------|------|------:|----:|------|-------------------------:|
| `host-inventory-prod` | db.m7g.8xlarge | 32 | 128 GB | Primary writer | ~$1,968 |
| `host-inventory-prod-read-only` | db.m7g.8xlarge | 32 | 128 GB | Primary read replica | ~$1,968 |
| `host-inventory-prod-secondary-read-only` | db.m7g.8xlarge | 32 | 128 GB | Secondary read replica | ~$1,968 |
| **Total** | | **96** | **384 GB** | | **~$5,904/mo** |

### Application Deployment

| Component | Pods | Gunicorn Config | Target DB |
|-----------|-----:|-----------------|-----------|
| `service` (nginx) | 5 | — | Routes GET/HEAD → reads, POST/PUT/DELETE → writes |
| `service-reads` | 10 | 4 workers × 8 threads | Primary read replica |
| `service-secondary-reads` | 10 | 4 workers × 8 threads | Secondary read replica |
| `service-writes` | 5 | 4 workers × 8 threads | Primary writer |
| MQ consumers (`pmin`) | 30 | — | Primary writer |
| MQ consumers (`p1`) | 10 | — | Primary writer |

The nginx reverse proxy (`service`) is the public API entrypoint. It routes requests
by HTTP method to the appropriate upstream:
- GET/HEAD → `host-inventory-service-reads` upstream (load-balanced across
  `service-reads` and `service-secondary-reads`)
- POST/PUT/DELETE/default → `host-inventory-service-writes` upstream

Key config: `MQ_DB_BATCH_MAX_MESSAGES: 50`, `INVENTORY_API_USE_READREPLICA: true`,
`HOSTS_TABLE_NUM_PARTITIONS: 32`, `MIGRATION_MODE: managed`.

### Observed Workloads

#### Primary Writer (`host-inventory-prod`)

| Metric | Peak | Baseline |
|--------|------|----------|
| CPUUtilization | ~30% | ~10% |
| DBLoad (AAS) | ~20 | ~5 |
| FreeableMemory | ~108 GB | stable |
| TotalIOPS | ~15K | ~5K |
| Actual RAM used | ~20 GB | stable |

Peaks correspond to nightly Kafka ingestion (MQ batch processing). With the
batch ingestion optimizations (PR #3734), we expect a **30–40% reduction** in
write-path DB load.

#### Primary Read Replica (`host-inventory-prod-read-only`)

| Metric | Peak (before SWATCH fix) | HBI-only (without SWATCH) |
|--------|--------------------------|---------------------------|
| CPUUtilization | ~18.9% | < 2% |
| DBLoad (AAS) | ~6.34 | **~0.26** |
| DBLoadRelativeToNumVCPUs | ~0.20 | ~0.008 |
| FreeableMemory | ~86.3 GB | stable |
| DatabaseConnections | ~217 | ~199 |

**Key finding:** The SWATCH team's `InventoryHost.streamFacts` query was consuming
**~4.49 AAS** — accounting for **~99% of the read replica's DB load** during its daily
batch window (~06:00–14:00 UTC). The root cause was missing `org_id` in the join
conditions against partitioned tables, forcing PostgreSQL to sequentially scan all 32
partitions (~5.3M rows) with a 506 MB disk sort.

A fix has been submitted
([rhsm-subscriptions PR #5846](https://github.com/RedHatInsights/rhsm-subscriptions/pull/5846))
that adds `org_id` to the join conditions and makes the `stale_timestamp` predicate
SARGable. This reduces execution time from **~8,139 ms to ~224 ms** per org (97%
reduction), effectively eliminating the SWATCH query as a DB load concern.

After the SWATCH fix is deployed, total read replica load will be **~0.26 AAS** — HBI's
own application queries only.

#### Secondary Read Replica (`host-inventory-prod-secondary-read-only`)

| Metric | Peak | Baseline |
|--------|------|----------|
| CPUUtilization | ~3.5% | < 1.75% |
| DBLoad (AAS) | ~1.14 | < 0.57 |
| DBLoadRelativeToNumVCPUs | ~0.04 | — |
| FreeableMemory | ~98.5 GB | stable |

Despite receiving traffic from 10 pods, this instance is nearly idle — HBI's read
workload is so light that even 10 pods produce negligible DB load. The observed
metrics are dominated by replication stream writes.

---

## Proposed Changes

### 1. Primary Writer: Downsize to `db.m8g.4xlarge`

| | Current | Proposed |
|---|---|---|
| **Instance** | db.m7g.8xlarge | db.m8g.4xlarge |
| **vCPUs** | 32 (Graviton3) | 16 (Graviton4) |
| **RAM** | 128 GB | 64 GB |
| **Effective compute** | 32 G3 cores | ~20–21 G3-equivalent (Graviton4 is ~30% faster per core) |
| **Max EBS IOPS** | 20,000 (current provisioned) | 20,000 |
| **Monthly cost** | ~$1,968 | ~$981 |
| **Savings** | | **~$987/mo (50%)** |

**Justification:**
- Actual RAM usage is ~20 GB; 64 GB provides 3x headroom.
- Peak DBLoad of ~20 AAS on 16 vCPUs = 1.25 DBLoad/vCPU. With batch optimizations
  reducing load by 30–40%, effective peak drops to ~12–14 AAS = 0.75–0.88 DBLoad/vCPU.
- Current provisioned IOPS (20K) is well within `db.m8g.4xlarge`'s 40K max — no
  storage bottleneck, and room to increase if needed.
- Graviton4's per-core improvement offsets the vCPU reduction.

**Risk:** Requires deploying batch ingestion optimizations (PR #3734) before or alongside
the downsize to ensure peak load stays within capacity.

### 2. Read Replicas: Consolidate to a Single Smaller Instance

With the SWATCH query fix deployed
([PR #5846](https://github.com/RedHatInsights/rhsm-subscriptions/pull/5846)), the
combined read load (HBI + optimized SWATCH) will be well under 1 AAS. Both read
replicas can be consolidated into a single, aggressively downsized instance.

| | Current (2 replicas) | Proposed (1 replica) |
|---|---|---|
| **Instance(s)** | 2x db.m7g.8xlarge | 1x db.m8g.xlarge |
| **vCPUs** | 64 total | 4 |
| **RAM** | 256 GB total | 16 GB |
| **Expected DBLoad/vCPU** | < 0.01 | < 0.07 |
| **Monthly cost** | ~$3,936 | ~$245 |
| **Savings** | | **~$3,691/mo (94%)** |

**Justification:**
- After the SWATCH fix, total read load is ~0.26 AAS. A 4 vCPU instance handles this
  with massive headroom.
- 16 GB RAM is sufficient — HBI's read working set is small and PostgreSQL will adapt
  its buffer cache.
- HBI retains a read replica for read-only failover mode during maintenance windows.

**Fallback:** If 16 GB proves too tight for buffer cache, step up to `db.m8g.2xlarge`:

| HBI replica size | Monthly cost | Savings vs current |
|-----------------|-------------:|-------------------:|
| db.m8g.xlarge (4 vCPU, 16 GB) | ~$245 | 94% |
| db.m8g.2xlarge (8 vCPU, 32 GB) | ~$490 | 87% |

**App changes:**
- Set `REPLICAS_SVC_SECONDARY_READS: 0`
- Increase `REPLICAS_SVC_READS` to 20 (absorb all read pods)
- Update `INVENTORY_API_READREPLICA_SECRET` to point to the new replica

### Cost Summary

| Component | Current | Proposed |
|-----------|--------:|---------:|
| Primary writer | $1,968 | $981 |
| Read replica(s) | $3,936 | $245 |
| **Total** | **$5,904** | **$1,226** |
| **Monthly savings** | — | **$4,678 (79%)** |
| **Annual savings** | — | **~$56K** |

---

## Rollout Plan

The rollout is designed to minimize risk and avoid downtime for read operations.
The primary writer downsize requires a brief maintenance window.

### Prerequisites

- [ ] Deploy batch ingestion optimizations
  ([HBI PR #3734](https://github.com/RedHatInsights/insights-host-inventory/pull/3734))
  to production
- [ ] Verify nightly peak DB metrics show expected 30–40% load reduction
- [ ] Deploy SWATCH query optimization
  ([rhsm-subscriptions PR #5846](https://github.com/RedHatInsights/rhsm-subscriptions/pull/5846))
  to production
- [ ] Verify read replica DB load drops to < 1 AAS after SWATCH fix
- [ ] Confirm read-only failover mode works with the new replica (test in staging)

### Phase 1: Consolidate Read Pods to Primary Replica (zero downtime)

**Goal:** Route all read traffic through a single read replica before downsizing.

1. **Point secondary read pods to the primary read replica**
   - Update `INVENTORY_API_SECONDARY_READREPLICA_SECRET` to use the same secret
     as `INVENTORY_API_READREPLICA_SECRET` (i.e., `host-inventory-read-only-db`)
   - Deploy the config change — `service-secondary-reads` pods now connect to the
     primary read replica alongside `service-reads` pods
   - All 20 read pods now hit the primary read replica

2. **Verify**
   - Confirm all read traffic flows through the primary read replica
   - Monitor primary read replica metrics for 24–48 hours
   - Verify no increase in read latency or error rates
   - Confirm secondary read replica shows zero application connections

3. **Decommission secondary read replica**
   - Once stable, delete the `host-inventory-prod-secondary-read-only` RDS instance
   - **Savings realized: ~$1,968/mo**

4. **Simplify deployments** (optional, can be done later)
   - Set `REPLICAS_SVC_SECONDARY_READS: 0`
   - Set `REPLICAS_SVC_READS: 20`
   - Remove `service-secondary-reads` from nginx upstream

### Phase 2: Downsize the Primary Read Replica (zero downtime)

**Goal:** Downsize the existing primary read replica in-place by temporarily
routing read traffic to the primary writer during the resize.

1. **Redirect read traffic to the primary writer**
   - Update `INVENTORY_API_READREPLICA_SECRET` to point to the primary writer
     endpoint (i.e., same as `INVENTORY_DB_SECRET`)
   - Rolling restart of read pods to pick up the new connection
   - Verify read pods are now querying the primary writer

2. **Downsize the read replica in-place**
   - Modify RDS instance type: `db.m7g.8xlarge` → `db.m8g.xlarge`
   - Expected downtime for the replica: **10–20 minutes** (instance modification
     + restart). Read traffic is unaffected — it's hitting the primary writer.
   - Wait for the replica to finish resizing and catch up (ReplicaLag → 0)

3. **Redirect read traffic back to the downsized replica**
   - Update `INVENTORY_API_READREPLICA_SECRET` to point back to the
     now-downsized `host-inventory-prod-read-only` endpoint
   - Rolling restart of read pods
   - Monitor for 24–48 hours — pay attention to:
     - Read latency (may increase slightly due to less buffer cache)
     - ReadIOPS (may increase due to smaller buffer cache)
     - FreeableMemory (should stabilize around 12–14 GB)
   - **Total read replica savings realized: ~$3,691/mo**

4. **Evaluate and adjust**
   - If read latency is unacceptable after 1 week, upgrade to
     `db.m8g.2xlarge` (still ~$3,446/mo savings)

### Phase 3: Downsize the Primary Writer (requires maintenance window)

**Goal:** Reduce the primary writer from `db.m7g.8xlarge` to `db.m8g.4xlarge`.

**This phase requires a brief downtime** because RDS instance type modification
triggers a restart.

1. **Pre-checks**
   - Confirm batch ingestion optimizations are deployed and showing reduced load
   - Verify nightly peak DBLoad is within `db.m8g.4xlarge` capacity
     (target: < 12 AAS sustained)
   - Schedule maintenance window during lowest-traffic period
     (weekday mid-morning UTC, between nightly peaks)

2. **Maintenance window execution**
   - Set HBI to read-only mode (traffic routes to read replica)
   - Stop MQ consumers to drain the ingestion pipeline
   - Modify RDS instance type: `db.m7g.8xlarge` → `db.m8g.4xlarge`
   - Expected downtime: **10–20 minutes** (RDS instance modification + restart)
   - Restart MQ consumers
   - Restore normal read/write mode

3. **Post-change monitoring**
   - Monitor the next nightly ingestion peak closely
   - Watch for: CPU > 80%, DBLoad/vCPU > 1.0, connection pool exhaustion
   - Keep the old instance type noted for quick rollback if needed
     (`modify-db-instance` back to `db.m7g.8xlarge`)

4. **Savings realized: ~$987/mo**

### Rollout Timeline

| Week | Phase | Action | Downtime | Savings |
|------|-------|--------|----------|---------|
| 1 | Prerequisites | Deploy batch optimizations + SWATCH fix, monitor | None | — |
| 2 | Phase 1 | Consolidate read pods, decommission secondary replica | None | $1,968/mo |
| 3 | Phase 2 | Downsize primary read replica in-place to db.m8g.xlarge (reads temporarily on primary writer) | None | $1,723/mo |
| 4+ | Phase 3 | Downsize primary writer to db.m8g.4xlarge | ~15 min | $987/mo |
| | **Total** | | | **$4,678/mo (~$56K/yr)** |

### Rollback Plan

Each phase is independently reversible:

- **Phase 1:** Re-create the secondary read replica, restore
  `INVENTORY_API_SECONDARY_READREPLICA_SECRET` to point to it
- **Phase 2:** Modify the read replica instance type back to `db.m7g.8xlarge`
  (requires another in-place resize with reads temporarily on the primary writer)
- **Phase 3:** Modify the primary writer instance type back to `db.m7g.8xlarge`
  (requires another ~15 min maintenance window)

---

## Appendix: SWATCH Query Optimization

### Problem

The SWATCH team's `InventoryHost.streamFacts` query was consuming **~4.49 AAS** on
the primary read replica during its daily batch window (~06:00–14:00 UTC). `EXPLAIN
ANALYZE` revealed the root cause: the joins against partitioned tables
(`system_profiles_static` and `system_profiles_dynamic`) used only `host_id`, missing
the `org_id` component of the composite primary key. This forced PostgreSQL to
sequentially scan all 32 partitions (~5.3M rows) with a 506 MB external merge sort
on disk.

### Fix

[rhsm-subscriptions PR #5846](https://github.com/RedHatInsights/rhsm-subscriptions/pull/5846)
applies two changes:

1. **Added `org_id` to JOIN conditions** — `h.org_id = sps.org_id` and
   `h.org_id = spd.org_id` enable partition pruning: PostgreSQL now scans only the
   single relevant partition instead of all 32.

2. **Made the `stale_timestamp` predicate SARGable** — changed from
   `NOW() < h.stale_timestamp + make_interval(...)` to
   `h.stale_timestamp > NOW() - make_interval(...)`, enabling direct index usage.

### Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Execution time (per org) | ~8,139 ms | ~224 ms | **97% faster (36x)** |
| Disk sort | 506 MB external merge | None (in-memory hash) | Eliminated |
| Partitions scanned (spd) | 32 (5.3M rows) | 1 | 97% fewer rows |
| Partitions scanned (sps) | 32 (740K lookups) | 1 (23K lookups) | 97% fewer lookups |

### HBI-Side Index Migration

An Alembic migration (`5691af9326b2_add_indexes_for_swatch_query.py`) has been
prepared to add supporting indexes:

```sql
CREATE INDEX idx_hosts_org_id_stale_timestamp ON hbi.hosts (org_id, stale_timestamp);
CREATE INDEX idx_hosts_billing_model ON hbi.hosts ((facts -> 'rhsm' ->> 'BILLING_MODEL'));
```

**Note on write cost:** The `stale_timestamp` index adds ~10–15% WriteIOPS during
nightly ingestion (stale_timestamp changes on every check-in). The billing model
index has negligible write cost. Monitor after deployment and drop if the write cost
outweighs the read benefit.
