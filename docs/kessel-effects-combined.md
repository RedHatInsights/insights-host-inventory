# Kessel Effects on Host Inventory Service - Combined Workflows

[← Back to Kessel Effects on HBI](kessel-effects-on-hbi.md)

## Overview

This document presents consolidated flowcharts showing all major workflows before and after Kessel integration. Each section starts with a single entry point and shows all possible scenarios side by side.

---

## Side-by-Side Comparison

| Aspect | Before Kessel | With Kessel |
|--------|--------------|-------------|
| **Authorization** | Single source (RBAC v1) | Hybrid (Kessel Authz + RBAC v1/v2) |
| **Host Grouping** | Optional - can be ungrouped | Mandatory - always in a group |
| **Ungrouped Hosts** | `groups` column set to `[]` | Auto-assigned to "Ungrouped Hosts" workspace |
| **Workflow Pattern** | HBI creates groups itself | Kessel creates the workspace, provides details to HBI to write to its DB |
| **Workspace Management** | HBI owned group creation and save to its DB | Kessel/RBAC v2 auto-create workspaces. HBI tells Kessel to created "Ungrouped Hosts |
| **Group Validation** | Check in HBI DB only | Check in RBAC v2 DB (source of truth) |
| **Host Data Storage** | HBI DB only | HBI DB (RBAC v2 has no host knowledge) |
| **Event Topics** | None | `outbox.event.workspace` |
| **Complexity** | Simple, straightforward | Complex, with wait states |

---

## Before Kessel

[← Back to Before Kessel Section](kessel-effects-on-hbi.md#before-kessel)

### Authorization Model

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','clusterBkg':'#ffffff','clusterBorder':'#000000','titleColor':'#000000','edgeLabelBackground':'#ffffff','nodeTextColor':'#000000'}}}%%
flowchart LR
    HBI[Host Inventory] --> RBAC[RBAC v1]
    RBAC --> HostPerms[Host Permissions]
    RBAC --> StalePerms[Staleness Permissions]
    RBAC --> GroupPerms[Group Permissions]
```

### Workflows Combined

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','clusterBkg':'#ffffff','clusterBorder':'#000000','titleColor':'#000000','edgeLabelBackground':'#ffffff','nodeTextColor':'#000000'}}}%%
flowchart TD
    Start[Host Inventory System]
    Start --> Entry{Entry Point}

    Entry -->|Kafka Message to Create Host| HC1[Receive Kafka MQ Message]
    Entry -->|API: Create Group| GC1[REST API Request]
    Entry -->|API: Add Host to Group| HG1[Add Host to Group Request]
    Entry -->|API: Remove Host| RG1[Remove Host from Group Request]

    %% Host Creation Flow
    HC1 --> HC2[Host Inventory Service]
    HC2 --> HC3[Create Host for Account]
    HC3 --> HC4[Set groups = blank/empty]
    HC4 --> HC5[Store in hosts table]
    HC5 --> HC6[✓ Host Created<br/>No Group]

    %% Group Creation Flow
    GC1 --> GC2[Host Inventory Service]
    GC2 --> GC3{Check RBAC v1<br/>Create Permission}
    GC3 -->|Denied| GC4[✗ Return Error]
    GC3 -->|Granted| GC5{Check if<br/>Group Exists}
    GC5 -->|Exists| GC8[✗ Return Error<br/>Group Already Exists]
    GC5 -->|Not Exists| GC6[Create Group]
    GC6 --> GC7[Store in groups table]
    GC7 --> GC9[✓ Group Created]

    %% Add Host to Group Flow
    HG1 --> HG2{Check RBAC v1<br/>Modify Permission}
    HG2 -->|Denied| HG3[✗ Return Error]
    HG2 -->|Granted| HG4{Check if<br/>Group Exists}
    HG4 -->|Not Exists| HG9[✗ Return Error<br/>Group Not Found]
    HG4 -->|Exists| HG5[Add to groups table]
    HG5 --> HG6[Update hosts_groups table]
    HG6 --> HG7[Update groups column in hosts]
    HG7 --> HG8[Update group host count]
    HG8 --> HG10[✓ Host Added to Group]

    %% Remove Host from Group Flow
    RG1 --> RG2{Check RBAC v1<br/>Modify Permission}
    RG2 -->|Denied| RG7[✗ Return Error]
    RG2 -->|Granted| RG3{Check if<br/>Group Exists}
    RG3 -->|Not Exists| RG5[✗ Return Error<br/>Group Not Found]
    RG3 -->|Exists| RG4[Remove Host-Group Association]
    RG4 --> RG5B[Set groups = blank]
    RG5B --> RG6[✓ Host Removed<br/>No Group]
```

### Key Characteristics - Before Kessel

- **Single Authorization Source**: RBAC v1 handles all permissions (hosts, staleness, groups)
- **Optional Group Membership**: Hosts can exist without being in a group (blank `groups` column)
- **Synchronous Operations**: Direct DB updates without event-driven coordination
- **Simple Workflows**: Straightforward request-response patterns
- **Four Main Entry Points**:
  1. **Kafka Message** → Host Creation (ungrouped)
  2. **API: Create Group** → Group Creation
  3. **API: Add Host to Group** → Host-Group Association
  4. **API: Remove Host** → Host becomes ungrouped

---

## With Kessel

[← Back to With Kessel Section](kessel-effects-on-hbi.md#with-kessel)

### Authorization Model

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','clusterBkg':'#ffffff','clusterBorder':'#000000','titleColor':'#000000','edgeLabelBackground':'#ffffff','nodeTextColor':'#000000'}}}%%
flowchart LR
    HBI[Host Inventory] --> KAuth[Kessel Authz]
    HBI --> RBACv1[RBAC v1]

    KAuth --> HostPerms[Host Permissions]
    KAuth --> StalePerms[Staleness Permissions]
    RBACv1 --> GroupPerms[Group Permissions]

    RBACv2[RBAC v2] -.Manages Workspaces.-> GroupPerms
```

### All Workflows

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','clusterBkg':'#ffffff','clusterBorder':'#000000','titleColor':'#000000','edgeLabelBackground':'#ffffff','nodeTextColor':'#000000'}}}%%
flowchart TD
    Start[Host Inventory System]
    Start --> Entry{Entry Point}

    Entry -->|Kafka Message to Create Host| KC1[Receive Kafka MQ Message]
    Entry -->|API: Create Group| KGC1[REST API Request]
    Entry -->|API: Add Host to Group| KHG1[Add Host to Group Request]
    Entry -->|API: Remove Host| KRG1[Remove Host from Group Request]

    %% Host Creation Flow - Always Grouped
    KC1 --> KC2[Host Inventory Service]
    KC2 --> KC3[Create Host in HBI DB<br/>groups = blank initially]
    KC3 --> KC4[Check RBAC v2 DB<br/>Request workspace_id for<br/>Ungrouped Hosts]
    KC4 --> KC5{Does Ungrouped Hosts<br/>Workspace Exist in RBAC v2?}
    KC5 -->|No| KC6[⚡ RBAC v2 Auto-Creates<br/>Ungrouped Hosts Workspace]
    KC5 -->|Yes| KC7[Get workspace_id from RBAC v2]
    KC6 --> KC8[⏳ Wait for Kafka Event<br/>outbox.event.workspace]
    KC8 --> KC9[Receive Workspace Event]
    KC7 --> KC9
    KC9 --> KC10[Create Group in HBI DB]
    KC10 --> KC11[Update groups column<br/>in hosts table]
    KC11 --> KC12[Update hosts_groups table]
    KC12 --> KC13[✓ Host Added <br/>to Ungrouped Hosts]

    %% Group Creation Flow
    KGC1 --> KGC2[Host Inventory Service]
    KGC2 --> KGC3{Check RBAC v1<br/>Create Permission}
    KGC3 -->|Denied| KGC4[✗ Return Error]
    KGC3 -->|Granted| KGC5{Check RBAC v2 DB<br/>Does Group Exist?}
    KGC5 -->|Yes| KGC8[✗ Return Error<br/>Group Already Exists]
    KGC5 -->|No| KGC6[Create Group in RBAC v2]
    KGC6 --> KGC7[Store in HBI groups table]
    KGC7 --> KGC9[✓ Group Created]

    %% Add Host to Group Flow
    KHG1 --> KHG2{Check RBAC v1<br/>Modify Permission}
    KHG2 -->|Denied| KHG3[✗ Return Error]
    KHG2 -->|Granted| KHG4{Check RBAC v2 DB<br/>Does Group Exist?}
    KHG4 -->|No| KHG9[✗ Return Error<br/>Group Not Found]
    KHG4 -->|Yes| KHG5[Update hosts_groups table<br/>in HBI DB]
    KHG5 --> KHG6[Update groups column<br/>in hosts table]
    KHG6 --> KHG7[Update group host count<br/>in HBI groups table]
    KHG7 --> KHG10[✓ Host Moved to Group]

    %% Remove Host from Group Flow - Auto Ungrouped
    KRG1 --> KRG2{Check RBAC v1<br/>Modify Permission}
    KRG2 -->|Denied| KRG10[✗ Return Error]
    KRG2 -->|Granted| KRG3{Check RBAC v2 DB<br/>Does Group Exist?}
    KRG3 -->|No| KRG8[✗ Return Error<br/>Group Not Found]
    KRG3 -->|Yes| KRG4[Remove from Current Group<br/>in HBI DB]
    KRG4 --> KRG5[⚡ Auto-Add to<br/>Ungrouped Hosts]
    KRG5 --> KRG6[Update hosts table<br/>groups column]
    KRG6 --> KRG7[Update HBI groups table<br/>host count]
    KRG7 --> KRG8B[Update hosts_groups table]
    KRG8B --> KRG9[✓ Host Removed<br/>Now in Ungrouped Hosts]
```

### Key Characteristics - With Kessel

- **Hybrid Authorization**: Kessel Authz (hosts/staleness) + RBAC v1 (groups) + RBAC v2 (workspace management)
- **Mandatory Group Membership**: Every host must belong to a group at all times
- **Event-Driven Architecture**: Asynchronous updates via Kafka topic `outbox.event.workspace`
- **Automatic Workspace Creation**: RBAC v2 auto-creates "Ungrouped Hosts" workspace when needed
- **RBAC v2 as Source of Truth**: All group existence validation checks RBAC v2 DB (returns Yes/No)
- **Separation of Concerns**: RBAC v2 manages groups/workspaces but has no knowledge of hosts; HBI DB stores all host data
- **Complex Workflows**: Event-driven patterns with wait states for coordination
- **Four Main Entry Points**:
  1. **Kafka Message** → Host Creation (always in a group - Ungrouped Hosts if not specified)
  2. **API: Create Group** → Group Creation (RBAC v2 DB check, then dual storage)
  3. **API: Add Host to Group** → Host moves between groups (RBAC v2 DB validation, HBI DB updates)
  4. **API: Remove Host** → Host automatically moves to Ungrouped Hosts (RBAC v2 DB validation, HBI DB updates)

---

## Related Resources

- [Kessel Project Documentation](https://project-kessel.github.io/)
- RBAC v1 and v2 integration documentation
- Kafka topic: `outbox.event.workspace` - Workspace lifecycle events
- [Original detailed documentation](kessel-effects-complete.md)
