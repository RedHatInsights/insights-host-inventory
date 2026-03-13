# /hbi-api-hosts-view - Query HBI hosts-view (host + app data) via the local REST API

Interact with the HBI hosts-view beta API running at `http://localhost:8080`. This endpoint returns host data combined with application metrics from Advisor, Vulnerability, Patch, Remediations, Compliance, and Malware.

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

Parse the arguments to determine the action. If no arguments are given, default to listing hosts with all app data.

## Actions

### List hosts with all app data (default)
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[app_data]=true&per_page=10' | python3 -m json.tool
```

### Get a specific host by UUID
If the user provides a UUID, fetch that host with all app data:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?hostname_or_id=<uuid>&fields[app_data]=true' | python3 -m json.tool
```

### Vulnerability view
If the user says `vuln` or `vulnerability`, list hosts sorted by critical CVEs descending:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[vulnerability]=true&order_by=vulnerability:critical_cves&order_how=DESC&per_page=10' | python3 -m json.tool
```

### Patch view
If the user says `patch`, list hosts with patch data sorted by installable RHSA advisories:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[patch]=true&order_by=patch:advisories_rhsa_installable&order_how=DESC&per_page=10' | python3 -m json.tool
```

### Advisor view
If the user says `advisor`, list hosts with advisor data sorted by recommendations:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[advisor]=true&order_by=advisor:recommendations&order_how=DESC&per_page=10' | python3 -m json.tool
```

### Compliance view
If the user says `compliance`, list hosts with compliance data sorted by last scan:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[compliance]=true&order_by=compliance:last_scan&order_how=DESC&per_page=10' | python3 -m json.tool
```

### Malware view
If the user says `malware`, list hosts with malware data sorted by last matches:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[malware]=true&order_by=malware:last_matches&order_how=DESC&per_page=10' | python3 -m json.tool
```

### Risky hosts
If the user says `risky`, show the riskiest hosts sorted by critical CVEs descending with all app data:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[app_data]=true&order_by=vulnerability:critical_cves&order_how=DESC&per_page=10' | python3 -m json.tool
```
After fetching, highlight hosts that have `critical_cves > 0` OR `incidents > 0` in the output.

### Custom filter
If the user says `filter <app_name> <field> <operator> <value>`, apply an app data filter.
Supported operators: eq, ne, gt, lt, gte, lte, nil, not_nil.
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?filter[<app_name>][<field>][<operator>]=<value>&fields[<app_name>]=true&per_page=10' | python3 -m json.tool
```
Example for `filter vulnerability critical_cves gte 1`:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?filter[vulnerability][critical_cves][gte]=1&fields[vulnerability]=true&per_page=10' | python3 -m json.tool
```

### Selective fields
If the user says `fields <app1> <app2> ...`, return only specified app types:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[<app1>]=true&fields[<app2>]=true&per_page=10' | python3 -m json.tool
```
Example for `fields advisor vulnerability`:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[advisor]=true&fields[vulnerability]=true&per_page=10' | python3 -m json.tool
```

### Custom sort
If the user says `sort <app:field> [ASC|DESC]`, sort by an app data field:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[app_data]=true&order_by=<app:field>&order_how=<direction>&per_page=10' | python3 -m json.tool
```
Example for `sort vulnerability:total_cves DESC`:
```bash
curl -s -H 'x-rh-identity: '"$IDENTITY" \
  'http://localhost:8080/api/inventory/v1/beta/hosts-view?fields[app_data]=true&order_by=vulnerability:total_cves&order_how=DESC&per_page=10' | python3 -m json.tool
```

## Supported query parameters

Standard host filters (pass as query parameters):
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
- `per_page` - Results per page (1-100, default: 50)
- `page` - Page number

Sorting:
- `order_by` - Sort by host field (`display_name`, `updated`, `operating_system`, `last_check_in`) OR app data field using `app:field` format
- `order_how` - Sort direction (`ASC`, `DESC`)

Sparse fieldsets:
- `fields[app_name]=true` - Return all fields for that app
- `fields[app_name]=field1,field2` - Return only specific fields
- `fields[app_data]=true` - Return all apps with all fields

App data filters:
- `filter[app_name][field][operator]=value` - Filter by app data (operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `nil`, `not_nil`)

## Available app types and fields

- **advisor**: `recommendations`, `incidents`
- **vulnerability**: `total_cves`, `critical_cves`, `high_severity_cves`, `cves_with_security_rules`, `cves_with_known_exploits`
- **patch**: `advisories_rhsa_applicable`, `advisories_rhba_applicable`, `advisories_rhea_applicable`, `advisories_other_applicable`, `advisories_rhsa_installable`, `advisories_rhba_installable`, `advisories_rhea_installable`, `advisories_other_installable`, `packages_applicable`, `packages_installable`, `packages_installed`, `template_name`, `template_uuid`
- **remediations**: `remediations_plans`
- **compliance**: `policies`, `last_scan`
- **malware**: `last_status`, `last_matches`, `total_matches`, `last_scan`

## Sortable app fields

These fields support `order_by=app:field` format:
- `advisor:recommendations`, `advisor:incidents`
- `vulnerability:total_cves`, `vulnerability:critical_cves`, `vulnerability:high_severity_cves`, `vulnerability:cves_with_security_rules`, `vulnerability:cves_with_known_exploits`
- `patch:advisories_rhsa_installable`, `patch:advisories_rhba_installable`, `patch:advisories_rhea_installable`, `patch:advisories_other_installable`, `patch:advisories_rhsa_applicable`, `patch:advisories_rhba_applicable`, `patch:advisories_rhea_applicable`, `patch:advisories_other_applicable`, `patch:packages_installable`, `patch:packages_applicable`, `patch:packages_installed`
- `remediations:remediations_plans`
- `compliance:last_scan`
- `malware:last_matches`, `malware:total_matches`, `malware:last_scan`

## Instructions

1. First, generate the identity header as described above.

2. Parse `$ARGUMENTS` to determine what the user wants. Examples:
   - (empty) -> list first 10 hosts with all app data
   - `<uuid>` -> get that specific host with all app data
   - `vuln` or `vulnerability` -> list hosts sorted by critical CVEs descending
   - `patch` -> list hosts with patch data sorted by installable advisories
   - `advisor` -> list hosts with advisor data sorted by recommendations
   - `compliance` -> list hosts with compliance data
   - `malware` -> list hosts with malware data
   - `risky` -> show riskiest hosts (high critical CVEs or advisor incidents)
   - `filter vulnerability critical_cves gte 1` -> custom app data filter
   - `fields advisor vulnerability` -> selective app data (only advisor and vulnerability)
   - `sort vulnerability:total_cves DESC` -> custom sort by app field
   - `help` -> print available sub-commands with examples

3. Build the appropriate curl command with the identity header. Note: this endpoint uses the `/beta/` prefix path: `/api/inventory/v1/beta/hosts-view`.

4. Run the command and present the results in a readable format:
   - For default/all app data: show a summary table with display_name, advisor recommendations, vulnerability critical_cves, patch installable counts, compliance policies, malware last_status
   - For app-specific views (vuln, patch, advisor, compliance, malware): show a table with display_name and all relevant fields for that app type
   - For single hosts: show full app_data in a structured format with each app as a section
   - For risky hosts: highlight hosts with critical_cves > 0 or incidents > 0 with risk indicators
   - Always show the total count and pagination info (total, page, per_page)

5. If the user says `help`, print this summary:
   ```
   /hbi-api-hosts-view — Query hosts with application data (beta)

   Sub-commands:
     (no args)                              List hosts with all app data (default)
     <uuid>                                 Get a specific host with all app data
     vuln                                   Vulnerability view — sorted by critical CVEs
     patch                                  Patch view — sorted by installable advisories
     advisor                                Advisor view — sorted by recommendations
     compliance                             Compliance view — sorted by last scan
     malware                                Malware view — sorted by last matches
     risky                                  Riskiest hosts — critical CVEs or incidents
     filter <app> <field> <op> <value>      Custom app data filter
     fields <app1> [app2] ...               Selective app data (only named apps)
     sort <app:field> [ASC|DESC]            Custom sort by app data field
     help                                   Show this help

   App types: advisor, vulnerability, patch, remediations, compliance, malware
   Filter operators: eq, ne, gt, lt, gte, lte, nil, not_nil

   Examples:
     /hbi-api-hosts-view                                        # all hosts, all app data
     /hbi-api-hosts-view vuln                                   # vulnerability-sorted view
     /hbi-api-hosts-view filter vulnerability critical_cves gte 1
     /hbi-api-hosts-view fields advisor vulnerability           # only advisor + vuln data
     /hbi-api-hosts-view sort patch:packages_installable DESC   # custom sort
   ```

6. If the API returns an error, show the error details and suggest fixes (e.g., is the service running? try `make hbi-health`). If a 404 or 501 is returned, remind the user that this is a beta/WIP endpoint at `/api/inventory/v1/beta/hosts-view`.
