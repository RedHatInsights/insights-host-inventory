# /api-groups - Query and manage HBI groups via the local REST API

Interact with the HBI groups API running at `http://localhost:8080`.

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

Parse the arguments to determine the action. If no arguments are given, default to listing groups.

## Actions

### List groups (default)
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/groups?per_page=20' | python3 -m json.tool
```

Supported filters:
- `name` - Filter by group name
- `group_type` - Filter by type (standard, ungrouped-hosts, all; default: standard)
- `order_by` - Sort by field (name, host_count, updated)
- `order_how` - Sort direction (ASC, DESC)
- `per_page` - Results per page (1-100)
- `page` - Page number

### Get group by ID
If the user provides a UUID:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/groups/<group_id>' | python3 -m json.tool
```

### List hosts in a group
If the user asks for hosts in a group:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/groups/<group_id>/hosts?per_page=20' | python3 -m json.tool
```

### Create a group
If the user asks to create a group:
```bash
curl -s -X POST -H "x-rh-identity: $IDENTITY" -H 'Content-Type: application/json' \
  -d '{"name": "<group_name>", "host_ids": []}' \
  'http://localhost:8080/api/inventory/v1/groups' | python3 -m json.tool
```

### Add hosts to a group
If the user asks to add hosts to a group:
```bash
curl -s -X POST -H "x-rh-identity: $IDENTITY" -H 'Content-Type: application/json' \
  -d '["<host_id_1>", "<host_id_2>"]' \
  'http://localhost:8080/api/inventory/v1/groups/<group_id>/hosts' | python3 -m json.tool
```

### Delete a group
If the user explicitly asks to delete a group:
```bash
curl -s -X DELETE -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/groups/<group_id>'
```
Always confirm with the user before deleting.

### Update a group
If the user asks to rename a group:
```bash
curl -s -X PATCH -H "x-rh-identity: $IDENTITY" -H 'Content-Type: application/json' \
  -d '{"name": "<new_name>"}' \
  'http://localhost:8080/api/inventory/v1/groups/<group_id>' | python3 -m json.tool
```

## Instructions

1. First, generate the identity header as described above.

2. Parse `$ARGUMENTS` to determine what the user wants. Examples:
   - (empty) -> list all groups
   - `<uuid>` -> get that specific group
   - `<uuid> hosts` -> list hosts in that group
   - `create <name>` -> create a new group
   - `name=mygroup` -> filter groups by name

3. Build the appropriate curl command with the identity header.

4. Run the command and present the results in a readable format:
   - For group lists: show a table with id, name, host_count, updated
   - For single groups: show all fields
   - For hosts in a group: show host table with id, display_name, updated

5. If the API returns an error, show the error details and suggest fixes.
