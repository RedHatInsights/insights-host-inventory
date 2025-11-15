# Kessel Effects on Host Inventory Service - Combined Workflows

[← Back to Kessel Effects on HBI](kessel-effects-on-hbi.md)

## Overview

This document presents consolidated flowcharts showing all major workflows before and after Kessel integration. Each section starts with a single entry point and shows all possible scenarios side by side.

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

    Entry -->|Kafka Message| HC1[Receive Kafka MQ Message]
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
    GC3 -->|Granted| GC5[Create Group]
    GC5 --> GC6[Store in groups table]
    GC6 --> GC7[✓ Group Created]

    %% Add Host to Group Flow
    HG1 --> HG2{Check RBAC v1<br/>Modify Permission}
    HG2 -->|Denied| HG3[✗ Return Error]
    HG2 -->|Granted| HG4[Add to groups table]
    HG4 --> HG5[Update hosts_groups table]
    HG5 --> HG6[Update groups column in hosts]
    HG6 --> HG7[Update group host count]
    HG7 --> HG8[✓ Host Added to Group]

    %% Remove Host from Group Flow
    RG1 --> RG2[Remove Host-Group Association]
    RG2 --> RG3[Set groups = blank]
    RG3 --> RG4[✓ Host Removed<br/>No Group]
```

### Key Characteristics - Before Kessel

- **Single Authorization Source**: RBAC v1 handles all permissions (hosts, staleness, groups)
- **Optional Group Membership**: Hosts can exist without being in a group (blank `groups` column)
- **Synchronous Operations**: Direct database updates without event-driven coordination
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

    Entry -->|Kafka Message| KC1[Receive Kafka MQ Message]
    Entry -->|API: Create Group| KGC1[REST API Request]
    Entry -->|API: Add Host to Group| KHG1[Add Host to Group Request]
    Entry -->|API: Remove Host| KRG1[Remove Host from Group Request]

    %% Host Creation Flow - Always Grouped
    KC1 --> KC2[Host Inventory Service]
    KC2 --> KC3[Create Host in DB<br/>groups = blank initially]
    KC3 --> KC4[Request workspace_id for<br/>Ungrouped Hosts from RBAC v2]
    KC4 --> KC5{Does Ungrouped Hosts<br/>Workspace Exist?}
    KC5 -->|No| KC6[⚡ RBAC v2 Auto-Creates<br/>Ungrouped Hosts Workspace]
    KC5 -->|Yes| KC7[Get workspace_id]
    KC6 --> KC8[⏳ Wait for Kafka Event<br/>outbox.event.workspace]
    KC8 --> KC9[Receive Workspace Event]
    KC7 --> KC9
    KC9 --> KC10[Create Group in HBI Database]
    KC10 --> KC11[Update groups column in hosts]
    KC11 --> KC12[Update hosts_groups table]
    KC12 --> KC13[✓ Host Created<br/>In Ungrouped Hosts]

    %% Group Creation Flow
    KGC1 --> KGC2[Host Inventory Service]
    KGC2 --> KGC3{Check RBAC v1<br/>Create Permission}
    KGC3 -->|Denied| KGC4[✗ Return Error]
    KGC3 -->|Granted| KGC5[Create Group]
    KGC5 --> KGC6[Store in groups table]
    KGC6 --> KGC7[✓ Group Created]

    %% Add Host to Group Flow
    KHG1 --> KHG2{Check RBAC v1<br/>Modify Permission}
    KHG2 -->|Denied| KHG3[✗ Return Error]
    KHG2 -->|Granted| KHG4[Add to groups table]
    KHG4 --> KHG5[Update hosts_groups table]
    KHG5 --> KHG6[Update groups column in hosts]
    KHG6 --> KHG7[Update group host count]
    KHG7 --> KHG8[✓ Host Moved to Group]

    %% Remove Host from Group Flow - Auto Ungrouped
    KRG1 --> KRG2[Remove from Current Group]
    KRG2 --> KRG3[⚡ Auto-Add to<br/>Ungrouped Hosts]
    KRG3 --> KRG4[Update hosts table]
    KRG4 --> KRG5[Update groups table]
    KRG5 --> KRG6[Update hosts_groups table]
    KRG6 --> KRG7[✓ Host Removed<br/>Now in Ungrouped Hosts]
```

### Key Characteristics - With Kessel

- **Hybrid Authorization**: Kessel Authz (hosts/staleness) + RBAC v1 (groups) + RBAC v2 (workspace management)
- **Mandatory Group Membership**: Every host must belong to a group at all times
- **Event-Driven Architecture**: Asynchronous updates via Kafka topic `outbox.event.workspace`
- **Automatic Workspace Creation**: RBAC v2 auto-creates "Ungrouped Hosts" workspace when needed
- **Complex Workflows**: Event-driven patterns with wait states for coordination
- **Four Main Entry Points**:
  1. **Kafka Message** → Host Creation (always in a group - Ungrouped Hosts if not specified)
  2. **API: Create Group** → Group Creation
  3. **API: Add Host to Group** → Host moves between groups
  4. **API: Remove Host** → Host automatically moves to Ungrouped Hosts

---

## Side-by-Side Comparison

| Aspect | Before Kessel | With Kessel |
|--------|--------------|-------------|
| **Authorization** | Single source (RBAC v1) | Hybrid (Kessel Authz + RBAC v1/v2) |
| **Host Grouping** | Optional - can be ungrouped | Mandatory - always in a group |
| **Ungrouped Hosts** | Blank `groups` column allowed | Auto-assigned to "Ungrouped Hosts" workspace |
| **Workflow Pattern** | Synchronous, direct DB updates | Asynchronous, event-driven (Kafka) |
| **Workspace Management** | N/A | RBAC v2 auto-creates workspaces |
| **Event Topics** | None | `outbox.event.workspace` |
| **Complexity** | Simple, straightforward | Complex, with wait states |

---

## Key Differences in Workflows

### 1. Host Creation
- **Before**: Simple 5-step process, host exists without group
- **After**: Complex 13-step process with RBAC v2 interaction, Kafka events, and mandatory group assignment

### 2. Group Creation
- **Before**: 7 steps with RBAC v1 check
- **After**: Same 7 steps (unchanged workflow)

### 3. Add Host to Group
- **Before**: 8 steps with RBAC v1 check
- **After**: 8 steps (similar workflow, but host is moving from one group to another)

### 4. Remove Host from Group
- **Before**: 4 steps, host becomes ungrouped
- **After**: 7 steps, host automatically assigned to "Ungrouped Hosts" workspace

---

## Related Resources

- [Kessel Project Documentation](https://project-kessel.github.io/)
- RBAC v1 and v2 integration documentation
- Kafka topic: `outbox.event.workspace` - Workspace lifecycle events
- [Original detailed documentation](kessel-effects-complete.md)
