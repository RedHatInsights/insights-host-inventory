# /hbi-api-staleness - Query and manage HBI staleness configuration via the local REST API

Interact with the HBI staleness API running at `http://localhost:8080`.

## Identity header

All requests require the `x-rh-identity` header. Before making any API call, generate the identity by looking up the org_id that has hosts in the database:

```bash
ORG_ID=$(podman compose -f dev.yml exec -T db psql -U insights -d insights -t -A -c \
  "SELECT org_id FROM hbi.hosts GROUP BY org_id ORDER BY count(*) DESC LIMIT 1;")
IDENTITY=$(python3 -c "
import base64, json
print(base64.b64encode(json.dumps({
    'identity': {'org_id': '${ORG_ID}', 'type': 'User', 'auth_type': 'basic-auth',
    'user': {'username': 'tuser@redhat.com', 'email': 'tuser@redhat.com',
    'first_name': 'test', 'last_name': 'user', 'is_active': True,
    'is_org_admin': False, 'is_internal': True, 'locale': 'en_US'}}
}, separators=(',', ':')).encode()).decode())
")
```

Use `$IDENTITY` in all curl calls below. If the DB query returns empty, fall back to org_id `test`.

## Arguments

The user may pass arguments: `$ARGUMENTS`

Parse the arguments to determine the action. If no arguments are given, default to showing the current staleness configuration.

## Actions

### Get current staleness configuration (default)
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/account/staleness' | python3 -m json.tool
```

### Get default staleness configuration
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/account/staleness/defaults' | python3 -m json.tool
```

### Create staleness configuration
If the user asks to set custom staleness values:
```bash
curl -s -X POST -H "x-rh-identity: $IDENTITY" -H 'Content-Type: application/json' \
  -d '{
    "conventional_time_to_stale": <minutes>,
    "conventional_time_to_stale_warning": <minutes>,
    "conventional_time_to_delete": <minutes>,
    "immutable_time_to_stale": <minutes>,
    "immutable_time_to_stale_warning": <minutes>,
    "immutable_time_to_delete": <minutes>
  }' \
  'http://localhost:8080/api/inventory/v1/account/staleness' | python3 -m json.tool
```

### Update staleness configuration
If the user asks to update specific staleness values:
```bash
curl -s -X PATCH -H "x-rh-identity: $IDENTITY" -H 'Content-Type: application/json' \
  -d '{"conventional_time_to_stale": <minutes>}' \
  'http://localhost:8080/api/inventory/v1/account/staleness' | python3 -m json.tool
```

### Delete staleness configuration (revert to defaults)
If the user asks to reset staleness to defaults:
```bash
curl -s -X DELETE -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/account/staleness'
```
Always confirm with the user before deleting.

## Staleness fields

All values are in **minutes**:
- `conventional_time_to_stale` - Time until a conventional host becomes stale
- `conventional_time_to_stale_warning` - Time until a conventional host gets a stale warning
- `conventional_time_to_delete` - Time until a conventional host is deleted
- `immutable_time_to_stale` - Time until an immutable (bootc/edge) host becomes stale
- `immutable_time_to_stale_warning` - Time until an immutable host gets a stale warning
- `immutable_time_to_delete` - Time until an immutable host is deleted

## Instructions

1. First, generate the identity header as described above.

2. Parse `$ARGUMENTS` to determine what the user wants. Examples:
   - (empty) -> show current staleness configuration
   - `defaults` -> show default staleness configuration
   - `reset` -> delete custom config (revert to defaults)
   - `set conventional_time_to_stale=1440` -> update a specific value

3. Build the appropriate curl command with the identity header.

4. Run the command and present the results in a readable format:
   - Show a table comparing conventional vs immutable staleness timings
   - Convert minutes to human-readable durations (e.g., 1440 minutes = 1 day)

5. If the API returns an error, show the error details and suggest fixes.
