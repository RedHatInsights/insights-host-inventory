# Kessel Effects on Host Inventory Service

## Overview

This document describes how the integration of Kessel impacts the Host-Based Inventory (HBI) service, focusing on changes to authorization models, automatic group assignment, and hosts synchronization workflows, and where the groups data is stored.

### What is [Kessel](https://project-kessel.github.io/):
In Kessel's own words?
> "In the simplest terms, Kessel is an inventory of resources, how they relate to one another, and how they change over time. A resource can be anything: a file, a virtual white board, a Linux host, a Kubernetes cluster, and so on."

From the HBI perspective, **hosts**, **staleness**, and **groups** are the resources that Kessel maintains inventory of.

## Key Differences Summary

| Aspect | Before Kessel | With Kessel |
|--------|--------------|-------------|
| **Authorization** | Single source (RBAC v1) | Hybrid (Kessel Authz + RBAC v1/v2) |
| **Host Permissions** | RBAC v1 | Kessel Authz |
| **Group Permissions** | RBAC v1 | RBAC v1 |
| **Workspace Management** | Not automatic | RBAC v2 auto-creates workspaces |
| **Host Grouping** | Optional - can be ungrouped | Mandatory - always in a group |
| **Ungrouped Hosts** | Allowed to not be in a group | Auto-assigned to "Ungrouped Hosts" workspace |
| **Group Validation** | Check in HBI DB only | Check in RBAC v2 DB (source of truth) |
| **Host Data Storage** | HBI DB only | **HBI DB** holds complete data about each host.  <br/>**RBAC DB** hosts workspaces data, and <br/>**Kessel Inventory DB** is aware of each host, by its ID, and which workspace each host is associated with.|
| **Workflow Pattern** | HBI creates groups itself | Kessel creates the workspace, provides details to HBI to write to its DB  |
**Event Topics** | `platform.inventory.events` | `platform.inventory.events` and `outbox.event.workspace` |
| **Host Synchronization** | Host Synchronization via Cyndi by producding Kafka events| Automatic sync with Kessel Inventory via outbox pattern |
| **Sync Trigger Fields** | N/A | `satellite_id`, `subscription_manager_id`, `insights_id`, `ansible_host`, `groups` |

## Impact on Authorization

The primary effect of Kessel on Host Inventory is how it interacts with RBAC (Role-Based Access Control):

- **Pre-Kessel**: RBAC v1 provided access permissions for all resources (hosts, staleness, and groups)
- **Post-Kessel**: Hybrid authorization model
  - **Kessel Authz**: Provides permissions for `hosts` and `staleness`
  - **RBAC v1**: Continues to provide permissions for `groups`
  - **RBAC v2**: Manages workspaces (groups) and serves as the source of truth for group existence
  - **Note**: In RBAC v2, groups are called "workspaces" and are stored in the RBAC v2 database

## Before Kessel

[**→ View Complete Flowchart: Before Kessel**](kessel-effects-combined.md#complete-workflow---before-kessel)

### Host Creation
1. Hosts were created upon receiving MQ (Kafka) messages
2. Host Inventory created hosts for the account from which the message was received
3. After creation, the `groups` column was blank or contained `[]`
4. Host data was stored in the `hosts` table

### Group Creation
1. Groups were created, updated, and deleted via REST API
2. When a group creation request was received:
   - Host Inventory checked with RBAC v1 for user permissions (Create Permission)
   - If permission denied, return error
   - If permission granted, check if group already exists in HBI DB
   - If group exists, return error
   - If group doesn't exist, create the group
   - Group data was stored in the `groups` table

### Host Addition to Group
1. RBAC v1 was checked for permission to modify the group (Modify Permission)
2. If permission denied, return error
3. If permission granted, check if group exists in HBI DB
4. If group doesn't exist, return error
5. If group exists:
   - New group record added to the `groups` table
   - `hosts_groups` table updated with the host-group association
   - Host's `groups` column updated
   - Group's host count updated (counted from `hosts_groups` table)

### Host Removal from Group
1. RBAC v1 was checked for permission to modify the group (Modify Permission)
2. If permission denied, return error
3. If permission granted, check if group exists in HBI DB
4. If group doesn't exist, return error
5. If group exists, remove host from group
6. When a host was removed from a group, the `groups` column was left blank

### Key Characteristics (Pre-Kessel)
1. RBAC v1 provided all permissions (hosts, staleness, groups)
2. Hosts could exist without group membership (blank `groups` column)
3. Group validation checked HBI DB only
4. Synchronous, direct DB updates
5. Simple workflows with straightforward request-response patterns

## With Kessel

[**→ View Complete Flowchart: With Kessel**](kessel-effects-combined.md#complete-workflow---with-kessel)

### Authorization Changes
- Kessel Authz holds permissions (view, update, or delete) for hosts and staleness
- RBAC v1 continues to provide permissions for groups (Create, Modify)
- RBAC v2 manages workspaces and serves as the source of truth for group existence validation

### Automatic Group Association
**Every host must be associated with a group.** When not explicitly assigned to a group, hosts are automatically associated with the **"Ungrouped Hosts"** group.

### Host Creation
1. Host Inventory creates the host and saves it to the HBI DB with blank `groups` column
2. Host Inventory checks RBAC v2 DB and requests the `workspace_id` for "Ungrouped Hosts"
3. Does the "Ungrouped Hosts" workspace exist in RBAC v2?
   - **No**: RBAC v2 auto-creates the "Ungrouped Hosts" workspace
     - Host Inventory waits for Kafka event on topic: `outbox.event.workspace`
     - Upon receiving the workspace event, continues to next step
   - **Yes**: Gets `workspace_id` from RBAC v2
4. Creates the group in HBI DB
5. Updates the `groups` column in `hosts` table
6. Updates the `hosts_groups` table
7. Host is now in "Ungrouped Hosts" group

### Group Creation
1. Host Inventory receives REST API request to create a group
2. Check RBAC v1 for Create Permission
   - **Denied**: Return error
   - **Granted**: Continue to next step
3. Check RBAC v2 DB: Does group exist?
   - **Yes**: Return error (Group Already Exists)
   - **No**: Continue to next step
4. Create group in RBAC v2
5. Store group in HBI groups table
6. Group created successfully

### Host Addition to Group
1. Host Inventory receives request to add host to a group
2. Check RBAC v1 for Modify Permission
   - **Denied**: Return error
   - **Granted**: Continue to next step
3. Check RBAC v2 DB: Does group exist?
   - **No**: Return error (Group Not Found)
   - **Yes**: Continue to next step
4. Update `hosts_groups` table in HBI DB
5. Update `groups` column in `hosts` table
6. Update group host count in HBI groups table
7. Host moved to group successfully

### Removing Host from Group
When a host is removed from a group:
1. Check RBAC v1 for Modify Permission
   - **Denied**: Return error
   - **Granted**: Continue to next step
2. Check RBAC v2 DB: Does group exist?
   - **No**: Return error (Group Not Found)
   - **Yes**: Continue to next step
3. Remove host from current group in HBI DB
4. Host is automatically added to the "Ungrouped Hosts" group
5. All relevant tables are updated in HBI DB:
   - `hosts` table (groups column)
   - `groups` table (host count)
   - `hosts_groups` table

### Hosts Synchronization with Kessel Inventory

Host-Based Inventory automatically synchronizes host data with Kessel Inventory through an event-driven outbox pattern. When certain critical host fields change, outbox entries are created that trigger synchronization events.

#### OUTBOX_TRIGGER_FIELDS

The following fields trigger synchronization with Kessel Inventory when they are created, updated, or deleted:

- **`satellite_id`** - Red Hat Satellite identifier for the host
- **`subscription_manager_id`** - Subscription Manager identifier
- **`insights_id`** - Red Hat Insights identifier
- **`ansible_host`** - Ansible host identifier
- **`groups`** - Group associations (workspace membership)

#### Synchronization Workflow

1. **Host Event Detection**: When a host is created, updated, or deleted, SQLAlchemy event listeners detect the change
2. **Field Change Detection**: The system checks if any of the `OUTBOX_TRIGGER_FIELDS` have changed
3. **Outbox Entry Creation**: If trigger fields changed, an outbox entry is automatically created

#### Automatic Synchronization Triggers

Outbox entries are created automatically in the following scenarios:

- **Host Creation**: All `OUTBOX_TRIGGER_FIELDS` are synchronized when a new host is created
- **Host Update**: Only when one or more `OUTBOX_TRIGGER_FIELDS` are modified
- **Host Deletion**: All host data is synchronized to indicate removal from inventory
- **Group Changes**: When hosts are added to or removed from groups (workspaces)

This ensures that Kessel Inventory maintains an accurate, real-time view of the host resources and their relationships, which is essential for proper authorization and resource management.

## Related Resources

- [Kessel Project Documentation](https://project-kessel.github.io/)
- RBAC v1 and v2 integration documentation
- Kafka topic: `outbox.event.workspace` - Workspace lifecycle events
