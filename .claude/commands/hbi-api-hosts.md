# /hbi-api-hosts - Query and manage HBI hosts via the local REST API

Interact with the HBI hosts API running at `http://localhost:8080`.

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

Parse the arguments to determine the action. If no arguments are given, default to listing hosts.

## Actions

### List hosts (default)
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts?per_page=10' | python3 -m json.tool
```

Supported filters the user can request (pass as query parameters):
- `display_name` - Filter by display name (case-insensitive)
- `fqdn` - Filter by FQDN
- `hostname_or_id` - Filter by display name, FQDN, or ID
- `insights_id` - Filter by insights ID (UUID)
- `provider_type` - Filter by provider (alibaba, aws, azure, gcp, ibm)
- `staleness` - Filter by staleness (fresh, stale, stale_warning, unknown)
- `registered_with` - Filter by reporter (insights, satellite, puptoo, rhsm-conduit)
- `system_type` - Filter by system type (conventional, bootc, edge)
- `tags` - Filter by tags (format: namespace/key=value)
- `group_name` - Filter by group name
- `order_by` - Sort by field (display_name, updated, operating_system, last_check_in)
- `order_how` - Sort direction (ASC, DESC)
- `per_page` - Results per page (1-100, default: 50)
- `page` - Page number

### Get host by ID
If the user provides a UUID, fetch that specific host:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>' | python3 -m json.tool
```

### Get system profile
If the user asks for the system profile of a host:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>/system_profile' | python3 -m json.tool
```

### Get host tags
If the user asks for tags on a host:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>/tags' | python3 -m json.tool
```

### Check if host exists
If the user provides an insights_id and asks to check existence:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/host_exists?insights_id=<uuid>' | python3 -m json.tool
```

### Delete host
If the user explicitly asks to delete a host by ID:
```bash
curl -s -X DELETE -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>'
```
Always confirm with the user before deleting.

### Update host
If the user asks to update display_name or ansible_host for a host:
```bash
curl -s -X PATCH -H "x-rh-identity: $IDENTITY" -H 'Content-Type: application/json' \
  -d '{"display_name": "<name>", "ansible_host": "<host>"}' \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>' | python3 -m json.tool
```

## Instructions

1. First, generate the identity header as described above.

2. Parse `$ARGUMENTS` to determine what the user wants. Examples:
   - (empty) -> list first 10 hosts
   - `stale` -> list hosts with staleness=stale
   - `<uuid>` -> get that specific host
   - `<uuid> profile` -> get system profile for that host
   - `<uuid> tags` -> get tags for that host
   - `display_name=myhost` -> filter by display name
   - `count` -> list hosts and report total count

3. Build the appropriate curl command with the identity header.

4. Run the command and present the results in a readable format:
   - For host lists: show a table with id, display_name, updated, staleness, OS info
   - For single hosts: show key fields in a structured format
   - For system profiles: show the profile fields in a readable format
   - Always show the total count and pagination info

5. If the API returns an error, show the error details and suggest fixes (e.g., is the service running? try `make hbi-health`).
