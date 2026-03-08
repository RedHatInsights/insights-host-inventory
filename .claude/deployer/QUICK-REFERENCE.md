# HBI Ephemeral Environment - Quick Reference

## Commands Cheat Sheet

```bash
/hbi-deploy              # Deploy environment (~7 min)
/hbi-verify-setup        # Verify health (~10 sec)
/hbi-test-iqe smoke      # Run smoke tests (~20 min)
/hbi-cleanup             # Delete environment (~30 sec)
```

## Common Workflows

### Quick Test
```bash
/hbi-deploy --duration 2h
/hbi-verify-setup
# ... your testing ...
/hbi-cleanup
```

### Full Day Development
```bash
/hbi-deploy --duration 8h
/hbi-verify-setup
# ... develop all day ...
/hbi-cleanup
```

### Run Tests
```bash
/hbi-deploy
/hbi-verify-setup
/hbi-test-iqe smoke
.claude/scripts/view-iqe-logs.sh --follow
/hbi-cleanup
```

## Port Forwards

After deployment, services available at:

| Service | URL | Use For |
|---------|-----|---------|
| HBI API | http://localhost:8000 | REST API testing |
| RBAC v2 | http://localhost:8111 | RBAC operations |
| Kessel Inventory | http://localhost:8222 | Inventory API |
| Unleash | http://localhost:4242 | Feature flags |
| HBI Database | localhost:5432 | Direct DB queries |
| RBAC Database | localhost:5433 | RBAC DB queries |
| Kessel Database | localhost:5434 | Kessel DB queries |
| Kafka | localhost:9092 | Messaging |

## Useful Commands

```bash
# Check namespace
bonfire namespace list

# Check pods
kubectl get pods -n <namespace>

# Check logs
kubectl logs -n <namespace> deployment/host-inventory-service

# Check port forwards
ps aux | grep "kubectl port-forward"

# Kill port forwards
pkill -f "kubectl port-forward"

# DB credentials
cat tmp/ephemeral_db_credentials_*.log

# Test HBI API
curl http://localhost:8000/health
```

## Scripts (Direct Execution)

```bash
# Deploy
.claude/deployer/deploy-ephemeral.sh --duration 24h

# Verify
.claude/scripts/verify-ephemeral-setup.sh

# Cleanup
.claude/scripts/remove-ephemeral-namespace.sh --force

# Deploy IQE pod
.claude/scripts/deploy-iqe-pod.sh <namespace> "smoke"

# View IQE logs
.claude/scripts/view-iqe-logs.sh --follow
```

## Troubleshooting Quick Fixes

```bash
# Not logged in?
oc login --token=<token> --server=https://api.crc-eph.r9lp.p1.openshiftapps.com:6443

# Port forwards stuck?
pkill -9 -f "kubectl port-forward"

# Deployment failed?
bonfire namespace describe <namespace>
kubectl get pods -n <namespace>
kubectl logs -n <namespace> <pod-name>

# Start fresh
/hbi-cleanup --force
/hbi-deploy
```

## File Locations

```
.claude/
├── commands/              # Slash command docs
│   ├── hbi-deploy.md
│   ├── hbi-verify-setup.md
│   ├── hbi-test-iqe.md
│   └── hbi-cleanup.md
├── deployer/              # Deployment scripts
│   ├── deploy-ephemeral.sh
│   ├── bonfire-deploy.sh
│   └── README-COMMANDS.md # Full documentation
└── scripts/               # Utility scripts
    ├── verify-ephemeral-setup.sh
    ├── remove-ephemeral-namespace.sh
    ├── deploy-iqe-pod.sh
    └── view-iqe-logs.sh

tmp/                       # Generated files
├── ephemeral_ports_*.log
└── ephemeral_db_credentials_*.log
```

## Exit Codes

All scripts return:
- `0` = Success
- `1` = Failure

Use in automation:
```bash
if /hbi-deploy; then
    echo "✅ Success"
else
    echo "❌ Failed"
fi
```

## Duration Format

```bash
--duration 2h      # 2 hours
--duration 8h      # 8 hours (work day)
--duration 24h     # 24 hours (1 day)
--duration 168h    # 168 hours (1 week)
--duration 335h    # 335 hours (2 weeks, default)
```

## Getting Help

```bash
/hbi-deploy --help
.claude/deployer/deploy-ephemeral.sh --help
```

Full documentation: `.claude/deployer/README-COMMANDS.md`
