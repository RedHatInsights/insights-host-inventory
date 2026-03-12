# HBI RDS Instance Downsizing Proposal

## Executive Summary

Analysis of production RDS metrics shows all three HBI database instances (primary writer
and two read replicas) are significantly oversized.

This proposal presents a plan to right-size the infrastructure, with projected savings
of **~87% on read replica costs** and **~50% on the primary writer** — totaling
**~$53K/year**.

---

## Current State

### Instances

| Instance | Type | vCPUs | RAM | Role | Monthly Cost (on-demand) |
|----------|------|------:|----:|------|-------------------------:|
| `host-inventory-prod` | db.m7g.8xlarge | 32 | 128 GB | Primary writer | ~$1,968 |
| `host-inventory-prod-read-only` | db.m7g.8xlarge | 32 | 128 GB | Primary read replica | ~$1,968 |
| `host-inventory-prod-secondary-read-only` | db.m7g.8xlarge | 32 | 128 GB | Secondary read replica | ~$1,968 |
| **Total** | | **96** | **384 GB** | | **~$5,904/mo** |

### Observed Workloads

#### Primary Writer (`host-inventory-prod`)

**Current metrics (pre-batch optimization):**

| Metric | Peak |
|--------|------|
| CPUUtilization | ~50% |
| DBLoad (AAS) | ~17 |
| DBLoad | ~19 |
| FreeableMemory | ~106 GB |
| TotalIOPS | ~18K |

Peaks correspond to nightly Kafka ingestion (MQ batch processing). Actual RAM
usage is ~22 GB at peak (128 GB - 106 GB freeable); the rest is available for
PostgreSQL buffer cache.

**Expected metrics after MQ batch optimization (PR #3734, 30–40% reduction):**

| Metric | Estimated Peak |
|--------|----------------|
| CPUUtilization | ~30–35% |
| DBLoad (AAS) | ~11–13 |
| DBLoad | ~12–14 |
| FreeableMemory | ~106 GB |
| TotalIOPS | ~12–14K |

#### Primary Read Replica (`host-inventory-prod-read-only`)

| Metric | Peak (before SWATCH fix) | HBI-only (without SWATCH) |
|--------|--------------------------|---------------------------|
| CPUUtilization | ~18.9% | < 2% |
| DBLoad (AAS) | ~6.34 | ~0.26 |
| FreeableMemory | ~86.3 GB | stable |

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

| Metric | Peak |
|--------|------|
| CPUUtilization | ~3.5% |
| DBLoad (AAS) | ~1.14 |
| FreeableMemory | ~98.5 GB |

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
- Actual RAM usage is ~22 GB at peak; 64 GB provides ~3x headroom.
- Current peak DBLoad is ~17 AAS. With batch optimizations reducing load by 30–40%,
  effective peak drops to ~11–13 AAS on 16 vCPUs = 0.69–0.81 DBLoad/vCPU.
- Current peak CPU is ~50% on 32 vCPUs. Post-batch, ~30–35% on 32 vCPUs translates
  to ~46–54% on 16 Graviton4 vCPUs (accounting for Graviton4's ~30% per-core improvement).
- Current provisioned IOPS (20K) is well within `db.m8g.4xlarge`'s 40K max — no
  storage bottleneck, and room to increase if needed.

**Risk:** Requires deploying batch ingestion optimizations (PR #3734) before or alongside
the downsize to ensure peak load stays within capacity.

### 2. Read Replicas: Consolidate to a Single Smaller Instance

With the SWATCH query fix deployed
([PR #5846](https://github.com/RedHatInsights/rhsm-subscriptions/pull/5846)), the
combined read load (HBI + optimized SWATCH) will be well under 1 AAS. Both read
replicas can be consolidated into a single, aggressively downsized instance.

| | Current (2 replicas) | Proposed (1 replica) |
|---|---|---|
| **Instance(s)** | 2x db.m7g.8xlarge | 1x db.m8g.2xlarge |
| **vCPUs** | 64 total | 8 |
| **RAM** | 256 GB total | 32 GB |
| **Expected DBLoad/vCPU** | < 0.01 | < 0.03 |
| **Monthly cost** | ~$3,936 | ~$490 |
| **Savings** | | **~$3,446/mo (87%)** |

**Justification:**
- After the SWATCH fix, total read load is ~0.26 AAS. An 8 vCPU instance handles this
  with massive headroom.
- 32 GB RAM provides comfortable buffer cache for both application reads and WAL replay
  during nightly ingestion peaks, minimizing replica lag risk.
- HBI retains a read replica for read-only failover mode during maintenance windows.

**App changes:**
- Set `REPLICAS_SVC_SECONDARY_READS: 0`
- Increase `REPLICAS_SVC_READS` to 20 (absorb all read pods)
- Update `INVENTORY_API_READREPLICA_SECRET` to point to the new replica

### Cost Summary

| Component | Current | Proposed |
|-----------|--------:|---------:|
| Primary writer | $1,968 | $981 |
| Read replica(s) | $3,936 | $490 |
| **Total** | **$5,904** | **$1,471** |
| **Monthly savings** | — | **$4,433 (75%)** |
| **Annual savings** | — | **~$53K** |

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
   - Modify RDS instance type: `db.m7g.8xlarge` → `db.m8g.2xlarge`
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
     - FreeableMemory (should stabilize around 28–30 GB)
   - **Total read replica savings realized: ~$3,446/mo**

### Phase 3: Downsize the Primary Writer (requires maintenance window)

**Goal:** Reduce the primary writer from `db.m7g.8xlarge` to `db.m8g.4xlarge`.

**This phase requires a brief downtime** because RDS instance type modification
triggers a restart.

1. **Pre-checks**
   - Confirm batch ingestion optimizations are deployed and showing reduced load
   - Verify nightly peak DBLoad is within `db.m8g.4xlarge` capacity
     (target: < 14 AAS sustained)
   - Schedule maintenance window during lowest-traffic period
     (weekday mid-morning UTC, between nightly peaks)

2. **Pre-maintenance communications**
   - Post an outage banner on the console.redhat.com website
   - Add a scheduled maintenance message to [status.redhat.com](https://status.redhat.com)

3. **Maintenance window execution**
   - Put HBI into read-only mode (all writes are rejected, reads continue
     via the read replica)
   - Stop MQ consumers to drain the ingestion pipeline
   - Modify RDS instance type: `db.m7g.8xlarge` → `db.m8g.4xlarge`
   - Expected write downtime: **10–20 minutes** (RDS instance modification + restart)
   - Restart the Debezium connector (Kessel outbox) following the
     [Tier 1 Postgres upgrade procedure](https://improved-adventure-16jykz5.pages.github.io/for-red-hatters/sp-runbooks/postgres-upgrade/#tier-1-procedure)
   - Restart MQ consumers
   - Restore HBI to normal read/write mode
   - Remove the outage banner and update [status.redhat.com](https://status.redhat.com) to resolved

4. **Post-change monitoring**
   - Monitor the next nightly ingestion peak closely
   - Watch for: CPU > 80%, DBLoad/vCPU > 1.0, connection pool exhaustion
   - Keep the old instance type noted for quick rollback if needed
     (back to `db.m7g.8xlarge`)

5. **Savings realized: ~$987/mo**

### Rollback Plan

Each phase is independently reversible:

- **Phase 1:** Re-create the secondary read replica, restore
  `INVENTORY_API_SECONDARY_READREPLICA_SECRET` to point to it
- **Phase 2:** Modify the read replica instance type back to `db.m7g.8xlarge`
  (requires another in-place resize with reads temporarily on the primary writer)
- **Phase 3:** Modify the primary writer instance type back to `db.m7g.8xlarge`
  (requires another ~15 min maintenance window)
