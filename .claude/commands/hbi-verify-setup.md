# /hbi-verify-setup - Verify HBI Ephemeral Environment Setup

Verify that an ephemeral HBI deployment is properly configured and running.

## What This Command Does

1. **Check Namespace** - Identifies active ephemeral namespace
2. **Verify Pods** - Ensures all pods are running
3. **Check Port Forwards** - Validates local port forwards are active
4. **Test API Health** - Tests HBI, RBAC v2, and Kessel APIs
5. **Verify Databases** - Connects to all three databases and checks data
6. **Check Configuration** - Validates .env file and credentials
7. **Check Feature Flags** - Verifies HBI Kessel feature flags in Unleash
8. **Report Summary** - Provides comprehensive status report

## Usage

```bash
/hbi-verify-setup
```

## What Gets Verified

**Namespace & Pods:**
- Ephemeral namespace existence and status
- Pod count and running state
- Key services: HBI, Kessel, RBAC v2, Kafka, PostgreSQL

**Port Forwards:**
- HBI API (8000)
- RBAC Service (8111)
- Kessel Inventory (8222, 9000)
- Kessel Relations (8333)
- Databases (5432, 5433, 5434)
- Kafka (9092, 29092)
- Kafka Connect (8083)
- Unleash (4242)

**API Health:**
- HBI API `/health` endpoint
- Basic connectivity tests

**Database Connectivity:**
- HBI Database: Check host count
- RBAC Database: Check workspace count
- Kessel Database: Check resource count

**Configuration Files:**
- `.env` database credentials
- `tmp/ephemeral_db_credentials_*.log`
- `tmp/ephemeral_ports_*.log`

**Feature Flags (Unleash):**
- `hbi.api.kessel-phase-1` - Kessel Phase 1 integration
- `hbi.api.kessel-groups` - Kessel groups support
- `hbi.api.kessel-force-single-checks-for-bulk` - Single check enforcement
- Status in development and production environments

## Prerequisites

- Active ephemeral deployment (via `/hbi-deploy`)
- Port forwards must be running
- Database credentials in `.env` file

## Output

Provides a comprehensive report with:
- ✅ Green checkmarks for successful verifications
- ❌ Red X marks for failures
- 📊 Data counts (hosts, workspaces, resources)
- 🔗 Active port forwards
- 📝 Summary of deployment status

## Related Commands

- `/hbi-deploy` - Deploy ephemeral environment
- `/hbi-doctor` - Health check your dev environment

## Implementation

This command uses: `.claude/scripts/verify-ephemeral-setup.sh`
