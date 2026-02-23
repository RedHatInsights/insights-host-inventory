# /hbi-deploy - Deploy HBI with Kessel to Ephemeral Environment

Deploy Host Inventory with Kessel, RBAC v2, and all dependencies to an ephemeral namespace.

## What This Command Does

1. **Prerequisites Check** - Validates oc, bonfire, kubectl installed
2. **Login to Cluster** - Authenticates to ephemeral cluster
3. **Reserve Namespace** - Creates or uses existing ephemeral namespace
4. **Deploy Services** - Deploys HBI, Kessel, RBAC with bonfire
5. **Setup Demo Data** - Creates connectors, users, and sample hosts
6. **Port Forwarding** - Sets up local port forwards for all services
7. **Get Credentials** - Retrieves database credentials
8. **Update .env** - Updates HBI .env file with new credentials
9. **Update /etc/hosts** - Updates Kafka bootstrap server entry

## Usage

```bash
/hbi-deploy
/hbi-deploy --duration 24h
/hbi-deploy --force
/hbi-deploy --duration 48h --force
```

## Options

- `--duration DURATION` - Namespace reservation duration (default: 335h)
- `--force` - Use existing namespace without prompting
- `--help` - Show help message

## Prerequisites

**Required Tools:**
- `oc` - OpenShift CLI
- `bonfire` - Red Hat's ephemeral environment tool
- `kubectl` - Kubernetes CLI

**Required Configuration:**
- Ephemeral cluster access (token + server URL)
- Podman (optional - for custom unleash image)
- Passwordless sudo (for /etc/hosts updates)

**Environment Variables:**
- `EPHEMERAL_TOKEN` - Auth token (or use `oc whoami -t`)
- `EPHEMERAL_SERVER` - Cluster server URL (or use `oc whoami --show-server`)

Get token from: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request

## What Gets Deployed

**Core Services:**
- Host Inventory (API + MQ service)
- Kessel Inventory API
- Kessel Relations API (SpiceDB)
- RBAC v2 Service
- Kafka + Zookeeper
- PostgreSQL (3 databases: HBI, RBAC, Kessel)
- Unleash (Feature Flags)

**Demo Data:**
- Test users from rbac_users_data.json
- 10 sample hosts (org_id: 12345)
- Kafka connectors (migration + outbox)
- SpiceDB schema

## Port Forwards

After deployment, these services are available locally:

| Service | Local Port | Description |
|---------|-----------|-------------|
| HBI API | 8000 | Host Inventory REST API |
| RBAC Service | 8111 | RBAC v2 API |
| Kessel Inventory | 8222 | Kessel Inventory API |
| Kessel Relations | 8333 | SpiceDB gRPC API |
| Kafka Bootstrap | 9092, 29092 | Kafka brokers |
| Kafka Connect | 8083 | Kafka Connect REST API |
| Feature Flags | 4242 | Unleash API |
| HBI Database | 5432 | PostgreSQL |
| RBAC Database | 5433 | PostgreSQL |
| Kessel Database | 5434 | PostgreSQL |

## Files Modified

- `$HBI_DIR/.env` - Database credentials updated
- `$HBI_DIR/tmp/ephemeral_ports.log` - Port forwarding log
- `$HBI_DIR/tmp/ephemeral_db_credentials.log` - Database credentials
- `/etc/hosts` - Kafka bootstrap server entry

## Output

Deployment logs and artifacts saved to `$HBI_DIR/tmp/`:
- Port forwarding processes
- Database credentials
- Namespace details

## Cleanup

When done with the ephemeral environment:

```bash
# Release namespace
bonfire namespace release <namespace>

# Stop port forwards
kudis  # Alias that kills all kubectl port-forward processes
```

## Troubleshooting

**"EPHEMERAL_TOKEN is not set"**
- Login first: `oc login --token=<token> --server=<server>`
- Or export variables manually

**"Failed to reserve namespace"**
- Check bonfire is installed: `bonfire --version`
- Check cluster access: `oc whoami`

**"Port forwarding failed"**
- Check pods are running: `oc get pods`
- Check existing port forwards: `kuports`
- Kill existing forwards: `kudis`

**"Deployment failed"**
- Check bonfire namespace: `bonfire namespace describe`
- Check pod logs: `oc logs <pod-name>`
- Release and retry: `bonfire namespace release <namespace>`

## Related Commands

- `/hbi-doctor` - Health check your dev environment
- `/hbi-maintenance` - Update dependencies and containers

## Implementation

This command uses:
- `.claude/deployer/deploy-ephemeral.sh` - Main orchestration
- `.claude/deployer/bonfire-deploy.sh` - Bonfire deployment logic
- `docs/set_hbi_rbac_ports.sh` - Port forwarding setup
- `docs/get_hbi_rbac_db_creds.sh` - Credential retrieval
