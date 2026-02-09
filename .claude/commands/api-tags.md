# /api-tags - Query HBI tags via the local REST API

Interact with the HBI tags API running at `http://localhost:8080`.

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

Parse the arguments to determine the action. If no arguments are given, default to listing all active tags.

## Actions

### List all active tags (default)
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/tags?per_page=50' | python3 -m json.tool
```

Supported filters:
- `search` - Search tags by namespace, key, or value
- `tags` - Filter by specific tags (format: namespace/key=value)
- `staleness` - Filter by host staleness (fresh, stale, stale_warning, unknown)
- `registered_with` - Filter by reporter
- `order_by` - Sort by field (tag, count; default: tag)
- `order_how` - Sort direction (ASC, DESC)
- `per_page` - Results per page (1-100)
- `page` - Page number

### Search tags
If the user provides a search term:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/tags?search=<term>&per_page=50' | python3 -m json.tool
```

### Get tags for a specific host
If the user provides a host UUID:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>/tags' | python3 -m json.tool
```

### Count tags for a specific host
If the user asks for tag count on a host:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>/tags/count' | python3 -m json.tool
```

## Instructions

1. First, generate the identity header as described above.

2. Parse `$ARGUMENTS` to determine what the user wants. Examples:
   - (empty) -> list all active tags
   - `search <term>` -> search tags matching the term
   - `<uuid>` -> get tags for that host
   - `<uuid> count` -> get tag count for that host
   - `order_by=count` -> list tags sorted by count

3. Build the appropriate curl command with the identity header.

4. Run the command and present the results in a readable format:
   - For tag lists: show a table with namespace, key, value, count
   - For host tags: show tags grouped by namespace

5. If the API returns an error, show the error details and suggest fixes.
