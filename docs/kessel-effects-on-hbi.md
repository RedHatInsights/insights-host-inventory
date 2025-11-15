# Kessel Effects on Host Inventory Service

## Overview

This document describes how the integration of Kessel impacts the Host-Based Inventory (HBI) service, focusing on changes to authorization models, automatic group assignment, and hosts synchronization workflows.

### What is [Kessel](https://project-kessel.github.io/):
> "In the simplest terms, Kessel is an inventory of resources, how they relate to one another, and how they change over time. A resource can be anything: a file, a virtual white board, a Linux host, a Kubernetes cluster, and so on."

From the HBI perspective, **hosts**, **staleness**, and **groups** are the resources that Kessel maintains inventory of.

## Impact on Authorization ([Flowchart](kessel-effects-complete.md#impact-on-authorization))

The primary effect of Kessel on Host Inventory is how it interacts with RBAC (Role-Based Access Control):

- **Pre-Kessel**: RBAC v1 provided access permissions for all resources (hosts, staleness, and groups)
- **Post-Kessel**: Hybrid authorization model
  - **RBAC v2**: Provides permissions for `hosts` and `staleness`
  - **RBAC v1**: Continues to provide permissions for `groups`
  - **Note**: In RBAC v2, groups are called "workspaces" and are stored in the RBAC database

## Before Kessel

### Host Creation ([Flowchart](kessel-effects-complete.md#host-creation))
1. Hosts were created upon receiving MQ (Kafka) messages
2. Host Inventory created hosts for the account from which the message was received
3. After creation, the `groups` column was blank or contained `[]`
4. Host data was stored in the `hosts` table

### Group Creation ([Flowchart](kessel-effects-complete.md#group-creation))
1. Groups were created, updated, and deleted via REST API
2. When a group creation request was received:
   - Host Inventory checked with RBAC v1 for user permissions
   - If permission granted, the group was created
   - Group data was stored in the `groups` table

### Host Addition to Group ([Flowchart](kessel-effects-complete.md#host-addition-to-group))
1. RBAC v1 was checked for permission to modify the group
2. If permission granted:
   - New group record added to the `groups` table
   - `hosts_groups` table updated with the host-group association
   - Host's `groups` column updated
   - Group's host count updated (counted from `hosts_groups` table)

### Host Removal from Group ([Flowchart](kessel-effects-complete.md#host-removal-from-group))
- When a host was removed from a group, the `groups` column was left blank

### Key Characteristics (Pre-Kessel)
1. RBAC v1 provided all permissions (hosts, staleness, groups)
2. Hosts could exist without group membership (blank `groups` column)

## With Kessel

### Authorization Changes
- Kessel Authz holds permissions (view, update, or delete) for hosts and statelenesst

### Automatic Group Association
**Every host must be associated with a group.** When not explicitly assigned to a group, hosts are automatically associated with the **"Ungrouped Hosts"** group.

### Host Creation ([Flowchart](kessel-effects-complete.md#host-creation-workflow))
1. Host Inventory creates the host and saves it to the database with blank `groups` column
2. Host Inventory requests the `workspace_id` for "Ungrouped Hosts" from RBAC v2
3. If the account doesn't have an "Ungrouped Hosts" group:
   - RBAC v2 creates one automatically
4. Host Inventory waits for the group creation event:
   - Listens for Kafka message on topic: `outbox.event.workspace`
5. Upon receiving the workspace event:
   - Creates the group in HBI database
   - Updates the `groups` value for the host in `hosts` table
   - Updates the `hosts_groups` table

### Removing Host from Group ([Flowchart](kessel-effects-complete.md#removing-host-from-group))
When a host is removed from a group:
1. Host is automatically added to the "Ungrouped Hosts" group
2. All relevant tables are updated:
   - `hosts` table
   - `groups` table
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

## Key Differences Summary

| Aspect | Before Kessel | After Kessel |
|--------|--------------|--------------|
| **Authorization Provider** | RBAC v1 only | Kessel Authz (RBAC v2) + RBAC v1 |
| **Host Permissions** | RBAC v1 | Kessel Authz |
| **Group Permissions** | RBAC v1 | RBAC v1 |
| **Ungrouped Hosts** | Allowed (blank `groups`) | Not allowed (auto-assigned to "Ungrouped Hosts") |
| **Group Creation** | Manual via API | Manual via API + automatic "Ungrouped Hosts" creation |
| **Event-Driven Updates** | No | Yes (Kafka topic: `outbox.event.workspace`) |
| **Host Synchronization** | No external synchronization | Automatic sync with Kessel Inventory via outbox pattern |
| **Sync Trigger Fields** | N/A | `satellite_id`, `subscription_manager_id`, `insights_id`, `ansible_host`, `groups` |

## Related Resources

- [Kessel Project Documentation](https://project-kessel.github.io/)
- RBAC v1 and v2 integration documentation
- Kafka topic: `outbox.event.workspace` - Workspace lifecycle events
