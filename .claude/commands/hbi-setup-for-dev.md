# /hbi-setup-for-dev - Setup Local Development Environment

Configure local development environment for an already-deployed HBI ephemeral namespace.

## What This Command Does

1. **Verify Namespace** - Checks that namespace exists and is accessible
2. **Health Check** - Verifies all required pods are running
3. **Port Forwarding** - Sets up local port forwards for all services
4. **Get Credentials** - Retrieves database credentials from Kubernetes secrets
5. **Update .env** - Updates HBI .env file with new credentials
6. **Update /etc/hosts** - Updates Kafka bootstrap server entry

**Note:** This command requires HBI to already be deployed. Run `/hbi-deploy` first if you haven't already.

## Usage

```bash
/hbi-setup-for-dev
/hbi-setup-for-dev --namespace ephemeral-abc123
```

## Options

- `--namespace NAMESPACE` - Use specific namespace (default: current kubectl context)
- `--help` - Show help message

## Prerequisites

**Required:**
- HBI already deployed (use `/hbi-deploy` first)
- Logged into ephemeral cluster (`oc login` or `kubectl` configured)
- Passwordless sudo (for /etc/hosts updates)

**Tools:**
- `oc` or `kubectl` - Kubernetes CLI
- `jq` - JSON processor

## Port Forwards

After running this command, these services are available locally:

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

- `$HBI_DIR/.env` - Database credentials updated (backup created)
- `$HBI_DIR/tmp/ephemeral_ports_<timestamp>.log` - Port forwarding log
- `$HBI_DIR/tmp/ephemeral_db_credentials_<timestamp>.log` - Database credentials
- `/etc/hosts` - Kafka bootstrap server entry (backup created in /tmp)

## Output

Logs and artifacts saved to `$HBI_DIR/tmp/`:
- Port forwarding processes
- Database credentials
- Timestamp for tracking

## After Setup

You can now run tests and development commands:

```bash
# Run unit tests
pipenv run pytest tests/

# Run specific test
pipenv run pytest tests/test_api_groups.py -v

# Access HBI API
curl http://localhost:8000/api/inventory/v1/health

# Access database
psql -h localhost -p 5432 -U <username> -d host-inventory
```

## Cleanup

When done:

```bash
# Kill all port-forwards
kudis  # Custom alias that kills all kubectl port-forward processes

# Or manually find and kill
ps aux | grep "kubectl port-forward"
kill <pid>
```

## Troubleshooting

**"No active namespace found"**
- Deploy HBI first: `/hbi-deploy`
- Or switch to ephemeral namespace: `oc project ephemeral-<id>`

**"Namespace does not exist"**
- Check available namespaces: `kubectl get namespaces | grep ephemeral`
- Deploy HBI first: `/hbi-deploy`
- Verify you're logged into the correct cluster

**"Required pods are missing"**
- The deployment may not be complete
- Check deployment status: `bonfire namespace describe`
- Re-run deployment: `/hbi-deploy`

**"Some pods are not in Running state"**
- Pods may still be starting - wait a few minutes
- Check pod logs: `kubectl logs -n <namespace> <pod-name>`
- Check pod events: `kubectl describe pod -n <namespace> <pod-name>`
- You'll be prompted if you want to continue anyway

**"Port forwarding failed"**
- Check pods are running: `kubectl get pods -n <namespace>`
- Check existing port forwards: `ps aux | grep port-forward`
- Kill existing forwards and retry: `pkill -f "kubectl port-forward"`

**"Passwordless sudo required"**
- Configure sudo without password for /etc/hosts updates
- Or manually update /etc/hosts after the script runs

**"Database credentials not found"**
- Check secret exists: `kubectl get secret host-inventory-db -n <namespace>`
- Check namespace is correct: `kubectl config current-context`
- Deployment may have failed - check pod status

## Example Workflow

```bash
# 1. Deploy HBI (if not already deployed)
/hbi-deploy --duration 24h

# 2. Setup local dev environment
/hbi-setup-for-dev

# 3. Run tests
pipenv run pytest tests/

# 4. When done, cleanup
/hbi-cleanup
```

## Related Commands

- `/hbi-deploy` - Deploy HBI to ephemeral environment
- `/hbi-verify-setup` - Verify deployment is healthy
- `/hbi-cleanup` - Cleanup ephemeral environment
- `/hbi-deploy-and-test` - Deploy and run tests in one command

## Implementation

This command uses:
- `.claude/deployer/setup-for-dev.sh` - Main setup script
- `docs/set_hbi_rbac_ports.sh` - Port forwarding setup
- `docs/get_hbi_rbac_db_creds.sh` - Credential retrieval
