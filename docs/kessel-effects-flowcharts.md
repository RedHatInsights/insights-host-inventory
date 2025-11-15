# Kessel Effects on Host Inventory - Process Flow Charts

This document provides visual flow charts for the key processes described in the Kessel Effects on Host Inventory Service documentation.

## Table of Contents
- [Before Kessel Workflows](#before-kessel-workflows)
  - [Host Creation (Pre-Kessel)](#host-creation-pre-kessel)
  - [Group Creation (Pre-Kessel)](#group-creation-pre-kessel)
  - [Host Addition to Group (Pre-Kessel)](#host-addition-to-group-pre-kessel)
  - [Host Removal from Group (Pre-Kessel)](#host-removal-from-group-pre-kessel)
- [With Kessel Workflows](#with-kessel-workflows)
  - [Host Creation Workflow (With Kessel)](#host-creation-workflow-with-kessel)
  - [Host Removal from Group (With Kessel)](#host-removal-from-group-with-kessel)
- [Authorization Comparison](#authorization-comparison)

---

## Before Kessel Workflows

### Host Creation (Pre-Kessel)

```mermaid
flowchart TD
    A[Kafka MQ Message Received] --> B[Host Inventory Service]
    B --> C[Create Host for Account]
    C --> D[Set groups column to blank/empty array]
    D --> E[Store Host Data in hosts table]
    E --> F[Host Creation Complete]

    style A fill:#e1f5ff
    style F fill:#c8e6c9
```

### Group Creation (Pre-Kessel)

```mermaid
flowchart TD
    A[REST API Request: Create Group] --> B[Host Inventory Service]
    B --> C{Check RBAC v1 for<br/>Create Permission}
    C -->|Permission Denied| D[Return Error]
    C -->|Permission Granted| E[Create Group]
    E --> F[Store Group Data in groups table]
    F --> G[Group Creation Complete]

    style A fill:#e1f5ff
    style D fill:#ffcdd2
    style G fill:#c8e6c9
```

### Host Addition to Group (Pre-Kessel)

```mermaid
flowchart TD
    A[Request: Add Host to Group] --> B{Check RBAC v1 for<br/>Modify Permission}
    B -->|Permission Denied| C[Return Error]
    B -->|Permission Granted| D[Add Group Record to groups table]
    D --> E[Update hosts_groups table<br/>with host-group association]
    E --> F[Update groups column<br/>in hosts table]
    F --> G[Update group host count<br/>from hosts_groups table]
    G --> H[Host Added to Group]

    style A fill:#e1f5ff
    style C fill:#ffcdd2
    style H fill:#c8e6c9
```

### Host Removal from Group (Pre-Kessel)

```mermaid
flowchart TD
    A[Request: Remove Host from Group] --> B[Remove Host-Group Association]
    B --> C[Set groups column to blank]
    C --> D[Host Removal Complete<br/>Host has no group]

    style A fill:#e1f5ff
    style D fill:#c8e6c9
```

---

## With Kessel Workflows

### Host Creation Workflow (With Kessel)

```mermaid
flowchart TD
    A[Kafka MQ Message Received] --> B[Host Inventory Service]
    B --> C[Create Host in Database<br/>groups column = blank]
    C --> D[Request workspace_id for<br/>Ungrouped Hosts from RBAC v2]
    D --> E{Does Ungrouped Hosts<br/>group exist?}
    E -->|No| F[RBAC v2 Creates<br/>Ungrouped Hosts Group]
    E -->|Yes| G[Get workspace_id]
    F --> H[Wait for Kafka Event<br/>Topic: outbox.event.workspace]
    H --> I[Receive Workspace Event]
    G --> I
    I --> J[Create Group in HBI Database]
    J --> K[Update groups column<br/>in hosts table]
    K --> L[Update hosts_groups table]
    L --> M[Host Creation Complete<br/>Host in Ungrouped Hosts]

    style A fill:#e1f5ff
    style H fill:#fff9c4
    style M fill:#c8e6c9
```

### Host Removal from Group (With Kessel)

```mermaid
flowchart TD
    A[Request: Remove Host from Group] --> B[Remove Host from Current Group]
    B --> C[Automatically Add Host to<br/>Ungrouped Hosts Group]
    C --> D[Update hosts table]
    D --> E[Update groups table]
    E --> F[Update hosts_groups table]
    F --> G[Host Removal Complete<br/>Host in Ungrouped Hosts]

    style A fill:#e1f5ff
    style C fill:#fff9c4
    style G fill:#c8e6c9
```

---

## Authorization Comparison

### Authorization Flow - Before Kessel

```mermaid
flowchart LR
    A[Host Inventory] --> B[RBAC v1]
    B --> C[Host Permissions]
    B --> D[Staleness Permissions]
    B --> E[Group Permissions]

    style A fill:#e1f5ff
    style B fill:#ffecb3
    style C fill:#c8e6c9
    style D fill:#c8e6c9
    style E fill:#c8e6c9
```

### Authorization Flow - With Kessel

```mermaid
flowchart LR
    A[Host Inventory] --> B[Kessel Authz<br/>RBAC v2]
    A --> C[RBAC v1]
    B --> D[Host Permissions]
    B --> E[Staleness Permissions]
    C --> F[Group Permissions]

    style A fill:#e1f5ff
    style B fill:#b39ddb
    style C fill:#ffecb3
    style D fill:#c8e6c9
    style E fill:#c8e6c9
    style F fill:#c8e6c9
```

---

## Key Workflow Changes

### Host Group Association - Comparison

```mermaid
flowchart TD
    subgraph Before["Before Kessel"]
        A1[Host Created] --> B1{Assigned to Group?}
        B1 -->|Yes| C1[Host in Group]
        B1 -->|No| D1[Host with No Group<br/>groups column = blank]
    end

    subgraph After["With Kessel"]
        A2[Host Created] --> B2[Always Assigned to Group]
        B2 --> C2{Explicitly Assigned?}
        C2 -->|Yes| D2[Host in Specified Group]
        C2 -->|No| E2[Host in Ungrouped Hosts<br/>Auto-created if needed]
    end

    style D1 fill:#ffcdd2
    style E2 fill:#fff9c4
    style C1 fill:#c8e6c9
    style D2 fill:#c8e6c9
```

---

## Legend

- 🔵 **Light Blue** - Start/Input events
- 🟡 **Yellow** - Important waiting/event-driven steps
- 🟢 **Green** - Completion/Success states
- 🔴 **Red** - Error/Denied states
- 🟣 **Purple** - Kessel Authz/RBAC v2
- 🟠 **Orange** - RBAC v1

---

## Notes

1. **Event-Driven Architecture**: The "With Kessel" workflows introduce Kafka-based event-driven updates (topic: `outbox.event.workspace`)
2. **Mandatory Group Association**: Post-Kessel, every host must belong to a group - the "Ungrouped Hosts" group serves as the default
3. **Hybrid Authorization**: Kessel uses both RBAC v2 (for hosts/staleness) and RBAC v1 (for groups/workspaces)
4. **Automatic Group Creation**: RBAC v2 automatically creates an "Ungrouped Hosts" workspace if it doesn't exist

---

## Related Documentation

- [Kessel Effects on Host Inventory Service](./kessel-effects-on-hbi.md) - Detailed documentation
- [Kessel Project Documentation](https://project-kessel.github.io/)
