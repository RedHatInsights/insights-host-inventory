# V1 → V2 API Endpoint Comparison

**Total operations: 41**

## Summary

| Category               | Count | V2 Change                                                        |
|------------------------|-------|------------------------------------------------------------------|
| Host_apps enrichment   | 6     | Host response adds `host_apps` data (superset of V1)             |
| Workspaces update      | 5     | Groups → Workspaces: 3 new fields + `updated` renamed `modified` |
| Views domain (beta→V2) | 7     | Graduate from `/beta/` prefix to V2                              |
| Unchanged              | 23    | Carry forward as-is                                              |

## V2 Hosts vs V1 Hosts

V2 host = V1 host + `host_apps` data. Purely additive, no breaking changes.

## V2 Workspaces vs V1 Groups — Field Changes

| Field         | V1 Group  | V2 Workspace       |
|---------------|-----------|---------------------|
| `parent_id`   | —         | **new**             |
| `description` | —         | **new**             |
| `type`        | —         | **new**             |
| `updated`     | `updated` | renamed `modified`  |

---

## Operations that return host data (need V2 update to add host_apps)

| #  | Method | Path                                       | V1 Response Schema                |
|----|--------|--------------------------------------------|-----------------------------------|
| 1  | GET    | `/hosts`                                   | HostQueryOutput (list of HostOut) |
| 2  | GET    | `/hosts/{host_id_list}`                    | HostQueryOutput                   |
| 3  | POST   | `/hosts/checkin`                           | HostOut                           |
| 4  | PATCH  | `/hosts/{host_id_list}`                    | (returns host)                    |
| 5  | GET    | `/hosts/{host_id_list}/system_profile`     | SystemProfileByHostOut            |
| 6  | GET    | `/groups/{group_id}/hosts`                 | HostQueryOutput                   |

These **6 operations** return host data and would need their response enriched with `host_apps`.

## Operations that return group data (need V2 update to workspaces)

| #  | Method | Path                          | V1 Response Schema   |
|----|--------|-------------------------------|----------------------|
| 1  | GET    | `/groups`                     | GroupOut              |
| 2  | POST   | `/groups`                     | GroupOutWithHostCount |
| 3  | PATCH  | `/groups/{group_id}`          | GroupOutWithHostCount |
| 4  | GET    | `/groups/{group_id_list}`     | GroupOut              |
| 5  | POST   | `/groups/{group_id}/hosts`    | GroupOutWithHostCount |

These **5 operations** return group data and need the workspaces update: + `parent_id`, `description`, `type`; `updated` → `modified`.

## Operations already built for V2 (views domain — moving from beta)

| #  | Method | Path                          | V1 Status   |
|----|--------|-------------------------------|-------------|
| 1  | GET    | `/beta/hosts-view`            | Implemented |
| 2  | GET    | `/beta/views`                 | 501 stub    |
| 3  | POST   | `/beta/views`                 | 501 stub    |
| 4  | GET    | `/beta/views/{view_id}`       | 501 stub    |
| 5  | PUT    | `/beta/views/{view_id}`       | 501 stub    |
| 6  | DELETE | `/beta/views/{view_id}`       | 501 stub    |
| 7  | POST   | `/beta/views/{view_id}/clone` | 501 stub    |

These **7 operations** are the views domain graduating from `/beta/` to V2.

## Operations that remain exactly the same (no change needed)

| #  | Method | Path                                      | Reason                         |
|----|--------|-------------------------------------------|--------------------------------|
| 1  | DELETE | `/hosts`                                  | No host body returned          |
| 2  | DELETE | `/hosts/all`                              | No host body returned          |
| 3  | DELETE | `/hosts/{host_id_list}`                   | No host body returned          |
| 4  | PATCH  | `/hosts/{host_id_list}/facts/{namespace}` | Facts operation, no host body  |
| 5  | PUT    | `/hosts/{host_id_list}/facts/{namespace}` | Facts operation, no host body  |
| 6  | GET    | `/hosts/{host_id_list}/tags`              | Returns tags, not hosts        |
| 7  | GET    | `/hosts/{host_id_list}/tags/count`        | Returns tag count              |
| 8  | GET    | `/host_exists`                            | Returns HostIdOut (just an ID) |
| 9  | DELETE | `/groups/{group_id_list}`                 | No body                        |
| 10 | DELETE | `/groups/{group_id}/hosts/{host_id_list}` | No body                        |
| 11 | DELETE | `/groups/hosts/{host_id_list}`            | No body                        |
| 12 | GET    | `/resource-types`                         | Returns resource types         |
| 13 | GET    | `/resource-types/inventory-groups`        | Returns resource type groups   |
| 14 | GET    | `/tags`                                   | Returns tags                   |
| 15 | GET    | `/system_profile/sap_system`              | Returns SAP aggregation        |
| 16 | GET    | `/system_profile/sap_sids`                | Returns SAP SIDs               |
| 17 | GET    | `/system_profile/operating_system`        | Returns OS aggregation         |
| 18 | POST   | `/system_profile/validate_schema`         | Validation result              |
| 19 | GET    | `/account/staleness`                      | Returns staleness config       |
| 20 | POST   | `/account/staleness`                      | Returns staleness config       |
| 21 | PATCH  | `/account/staleness`                      | Returns staleness config       |
| 22 | DELETE | `/account/staleness`                      | No body                        |
| 23 | GET    | `/account/staleness/defaults`             | Returns defaults               |
