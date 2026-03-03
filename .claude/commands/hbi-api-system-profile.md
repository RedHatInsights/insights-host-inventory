# /hbi-api-system-profile - Query HBI system profile data via the local REST API

Interact with the HBI system profile API running at `http://localhost:8080`.

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

Parse the arguments to determine the action. If no arguments are given, show available sub-commands.

## Actions

### Get system profile for a host
If the user provides a host UUID:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>/system_profile' | python3 -m json.tool
```

Optionally filter fields with the `fields[system_profile]` parameter to only return specific fields:
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/hosts/<host_id>/system_profile?fields[system_profile]=operating_system,cpu_model,number_of_cpus,arch' | python3 -m json.tool
```

### Get operating system distribution
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/system_profile/operating_system?per_page=50' | python3 -m json.tool
```

Supported filters:
- `staleness` - Filter by host staleness
- `tags` - Filter by tags
- `registered_with` - Filter by reporter

### Get SAP system data
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/system_profile/sap_system' | python3 -m json.tool
```

### Get SAP SIDs
```bash
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8080/api/inventory/v1/system_profile/sap_sids?per_page=50' | python3 -m json.tool
```

Supports `search` parameter to filter SIDs.

## Available system profile fields

CPU: cpu_model, number_of_cpus, number_of_sockets, cores_per_socket, threads_per_core
Memory: system_memory_bytes
OS: operating_system, arch, kernel_version
BIOS: bios_vendor, bios_version, bios_release_date
Network: network_interfaces, public_ipv4_addresses, public_dns
Storage: disk_devices
Cloud: infrastructure_type, infrastructure_vendor, cloud_provider
Management: satellite_managed, katello_agent_running
SAP: sap_system, sap_sids, sap_instance_number, sap_version
Packages: installed_packages, installed_products
Services: installed_services, enabled_services, running_processes
Other: last_boot_time, insights_client_version, host_type, system_update_method, bootc_status

## Instructions

1. First, generate the identity header as described above.

2. Parse `$ARGUMENTS` to determine what the user wants. Examples:
   - `<uuid>` -> get full system profile for that host
   - `<uuid> os` or `<uuid> operating_system` -> get just OS info for that host
   - `<uuid> cpu` -> get CPU-related fields for that host
   - `os` or `operating_system` -> get OS distribution across all hosts
   - `sap` -> get SAP system data across all hosts
   - `sap_sids` -> get SAP SIDs across all hosts

3. Build the appropriate curl command with the identity header.

4. Run the command and present the results in a readable format:
   - For host system profiles: show key fields in a structured format
   - For OS distribution: show a table with OS name, major.minor version, count
   - For SAP data: show a table with values and counts

5. If the API returns an error, show the error details and suggest fixes.
