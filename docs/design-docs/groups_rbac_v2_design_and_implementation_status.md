# RBAC v2 Migration - Implementation Status

> **Author:** Arif<br/>
> **Branch:** rhineng-17393<br/>
> **Last Updated:** 2025-12-09<br/>

---

## Overview

Migration of Groups endpoints from Host Inventory database-backed groups to RBAC v2 workspaces.

**Status Summary:** <br/>
  - [RHINENG-17393](https://issues.redhat.com/browse/RHINENG-17): Update GET /groups to use RBAC_v2.   ✅ **Complete**.  Delivery **blocked** by [RHCLOUD-42653](https://issues.redhat.com/browse/RHCLOUD-42653)<br/>
  - [RHINENG-17397](https://issues.redhat.com/browse/RHINENG-17397): Update GET /groups/{group_id_list} to use RBAC v2. Delivery **blocked** by [RHCLOUD-43362](https://issues.redhat.com/browse/RHCLOUD-43362)<br/>
  - [RHINENG-17399](https://issues.redhat.com/browse/RHINENG-17399): Update POST /groups/{group_id}/hosts to use RBAC v2. Delivery **blocked** by [RHCLOUD-43362](https://issues.redhat.com/browse/RHCLOUD-43362)<br/>
  - [RHINENG-17400](https://issues.redhat.com/browse/RHINENG-17400): Update DELETE /groups/{group_id}/hosts/{host_id_list} to use RBAC v2. Delivery **blocked** by [RHCLOUD-43362](https://issues.redhat.com/browse/RHCLOUD-43362)<br/>
  - [RHINENG-21605](https://issues.redhat.com/browse/RHINENG-21605): Add GET endpoint for /groups/{group_id}/hosts. Delivery **blocked** by [RHCLOUD-43362](https://issues.redhat.com/browse/RHCLOUD-42653)<br/>

**Feature Flags:**<br/>
  - `FLAG_INVENTORY_KESSEL_PHASE_1` - Used for GET /groups (RHINENG-17393)<br/>
  - `FLAG_INVENTORY_KESSEL_GROUPS` - Defined but not yet integrated for RHINENG-17397, RHINENG-17399, RHINENG-17400, RHINENG-21605)<br/>

---

## Group Object (RBAC v1) vs Workspace Object (RBAC v2)

### RBAC v1 - Group Object (Database)

**Source:** PostgreSQL `groups` table

**JSON Object** provided by database query
```json
{
  "id": "019a5ae6-69bf-7323-bc60-f075715034c8",
  "org_id": "12345",
  "account": "123",
  "name": "Production Servers",
  "ungrouped": false,
  "created": "2025-11-06T20:40:41.233648+00:00",
  "updated": "2025-11-06T20:40:41.233653+00:00",
  "host_count": 10
}
```

---

### RBAC v2 - Workspace Object (API)

**Source:** RBAC v2 API (`GET /api/rbac/v2/workspaces/`)

**Dict Object** provided by RBAC v2 API
```json
{
  "id": "019a5ae6-69bf-7323-bc60-f075715034c8",
  "org_id": "12345",
  "parent_id": "019a5ae6-3a1e-7840-b3ff-2b1c533d187c",
  "name": "Production Servers",
  "description": null,
  "type": "standard",
  "created": "2025-11-06T20:40:41.151481Z",
  "modified": "2025-11-06T20:40:41.160109Z",
  "host_count": 10
}
```

---

### Field Mapping

| Field | RBAC v1 | RBAC v2 | Transformation |
|-------|---------|---------|----------------|
| **id** | ✅ UUID | ✅ UUID | None |
| **name** | ✅ string | ✅ string | None |
| **org_id** | ✅ string | ✅ string | None |
| **account** | ✅ string | ❌ Missing | Inject from identity (currently NULL) |
| **ungrouped** | ✅ boolean | ❌ Missing | **NOT DERIVED** (serialization gap) |
| **created** | ✅ datetime | ✅ datetime | None |
| **updated** | ✅ datetime | ✅ `modified` | Rename `modified` → `updated` |
| **parent_id** | ❌ N/A | ✅ UUID | **Included in output** (extra field) |
| **description** | ❌ N/A | ✅ string | **Included in output** (extra field) |
| **type** | ❌ N/A | ✅ string | **Included in output** (extra field) |
| **host_count** | ✅ Computed | ✅ Computed | Fetched via database JOIN |

---

### Serialization Functions

Serialization functions will be updated to:
1. Deal with differences in the objects provided by the legacy implementation and RBAC_v2
2. Add `account` to the workspace object provided by RBAC-v2.

No change required to get host_count as it is provided by Host Inventory

---

## Implementation Details (High Level)
### RHINENG-17393: GET /groups (List All Groups)
#### Status: ✅ COMPLETE
This work is complete unless groups and worspaces serialization is to be changed

__Endpoint:__ `GET /api/inventory/v1/groups`<br/>
<!-- __File__ `api/group.py:60-83`<br/> -->
__Feature Flag:__ `FLAG_INVENTORY_KESSEL_PHASE_1` (enabled → RBAC v2, disabled → database)<br/>
<!-- __Commit:__ 77bddf10 -->

### Implementation

__Function__ `get_group_list()`<br/>
- __Location:__ `api/group.py`<br/>
- __Input Parameters__<br/>
  - `name` (string, optional) - Filter by partial name match<br/>
  - `page` (int, default=1) - Page number<br/>
  - `per_page` (int, default=100) - Items per page<br/>
  - `order_by` (string, optional) - Sort field (⚠️ ignored in RBAC v2 mode<br/>
  - `order_how` (string, optional) - Sort direction (⚠️ ignored in RBAC v2 mode)<br/>
  - `group_type` (string, optional) - Filter: `standard`, `ungrouped-hosts`<br/>
  - `rbac_filter` (dict) - RBAC permissions<br/>
- __Output:__ `{"total": int, "count": int, "page": int, "per_page": int, "results": [...]}`<br/>

**RBAC v2 Integration Functions:**<br/>
1. `get_rbac_workspaces()` (`lib/middleware.py`)<br/>
   - __Input:__ `name, offset, limit, rbac_filter, group_type, identity`<br/>
   - __Output:__ `(workspace_list: list[dict], total: int)`<br/>
   - __Action:__ Calls RBAC v2 API, applies pagination and filtering<br/>

2. `serialize_workspace_without_host_count()` (`app/serialization.py`)<br/>
   - __Input:__ `group: dict, org_id: str`<br/>
   - __Output:__ Serialized workspace dict with renamed `modified` → `updated`<br/>

3. `get_non_culled_hosts_count_in_group()` (`lib/host_repository.py`)<br/>
   - __Input:__ `group_id, org_id`<br/>
   - __Output:__ `int` (host count from database)<br/>

### Tests

__Existing:__ `tests/test_api_groups_get.py` (13 tests)
- Coverage: Basic GET /groups endpoint, pagination, filtering, RBAC permissions
- RBAC v2 tests: `tests/test_rbac_v2.py` (8 tests covering workspace integration)

**Test Coverage:** ✅ Adequate

### Known Issues

⚠️ **RHCLOUD-42653:** RBAC v2 API lacks sorting support<br/>
- __Impact:__ `order_by` and `order_how` parameters ignored when feature flag enabled<br/>
- __Workaround:__ None<br/>
- __Status:__ Tracked with RBAC v2 team<br/>

---

## RHINENG-17397: GET /groups/{group_id_list} (Get Groups by IDs)

### Status: ⚠️ BLOCKED (RBAC v2 API Limitation)

__Endpoint:__ `GET /api/inventory/v1/groups/{group_id_list}`<br/>
<!-- **File:** `api/group.py:261-281` --><br/>
__Current State:__ Uses database only (no RBAC v2 integration)<br/>

### Implementation Gap

__Function:__ `get_groups_by_id()`<br/>
<!-- - **Location:** `api/group.py:261`<br/> -->
- **Current Behavior:** Queries database directly, no feature flag check<br/>
- **Required:** Feature flag check + RBAC v2 workspace batch fetch<br/>

### Blocker

⚠️ **RHCLOUD-43362:** RBAC v2 API doesn't support multiple workspace IDs<br/>
- **Impact:** Cannot batch fetch workspaces by ID list<br/>
- **Options:**<br/>
  1. Wait for RBAC v2 API enhancement (recommended)<br/>
  2. Sequential API calls (N+1 performance concern)<br/>

### Missing Functions

**Required:** `get_rbac_workspaces_by_ids()` in (`lib/middleware.py`)<br/>
- **Input:** `workspace_ids: list[str], identity: Identity`<br/>
- **Output:** `list[dict]` (workspace objects)<br/>
- **Action:** Batch fetch workspaces from RBAC v2 API<br/>

### Tests

**Existing:** `tests/test_api_groups_get.py` (database tests only)<br/>
**Needed:** RBAC v2 integration tests when blocker resolved<br/>

### Next Steps

1. Wait for RHCLOUD-43362 resolution<br/>
2. Implement `get_rbac_workspaces_by_ids()` function<br/>
3. Add feature flag check to `get_groups_by_id()`<br/>
4. Add RBAC v2 integration tests<br/>

---

## RHINENG-17399: POST /groups/{group_id}/hosts (Add Hosts to Group)

### Status: ❌ PENDING (Missing Function)

**Endpoint:** `POST /api/inventory/v1/groups/{group_id}/hosts`<br/>
<!-- **File:** `api/host_group.py:37-64`<br/> -->
**Current State:** Uses database validation only, no RBAC v2 integration<br/>

### Implementation Gap

**Function:** `add_host_list_to_group()`<br/>
- **Location:** `api/host_group.py:37`<br/>
- **Input Parameters:**<br/>
  - `group_id` (UUID) - Target group/workspace ID<br/>
  - `host_id_list` (list[UUID]) - Hosts to add<br/>
  - `rbac_filter` (dict) - RBAC permissions<br/>
- **Output:** Updated group with hosts<br/>
- **Current Behavior:** Validates group via database (`get_group_by_id_from_db()`)<br/>
- **Required:** Feature flag check + RBAC v2 workspace validation<br/>

### Missing Functions

**Required:** `get_rbac_workspace_by_id()` (`lib/middleware.py`)<br/>
- **Input:** `workspace_id: str, identity: Identity`<br/>
- **Output:** `dict` (workspace object)<br/>
- **Action:** Fetch single workspace from RBAC v2 API<br/>
- **Error:** Raise `ResourceNotFoundException` if workspace not found<br/>

### Implementation Plan

<!-- **File:** `api/host_group.py:37-64`<br/> -->

1. **Add feature flag check** <!-- (line 48)-->:
   - If `FLAG_INVENTORY_KESSEL_GROUPS` enabled → call `get_rbac_workspace_by_id()`<br/>
   - If disabled → use existing database query<br/>

2. **Add workspace validation:**<br/>
   - Call `get_rbac_workspace_by_id(group_id, identity)`<br/>
   - Return 404 if workspace not found<br/>
   - Proceed with existing host association logic (database)<br/>

3. **No changes to host association logic:**<br/>
   - Host-to-group mappings remain in database<br/>
   - Only workspace validation changes<br/>

### Tests

**Existing:** `tests/test_api_host_group.py`<br/>
- 16 tests covering add hosts functionality<br/>
- Tests RBAC permissions, validation, edge cases<br/>

**Needed:** New tests in `tests/test_api_host_group.py`<br/>
1. `test_add_hosts_with_rbac_v2_workspace_validation()`<br/>
   - Mock `get_rbac_workspace_by_id()` to return workspace<br/>
   - Verify hosts added successfully<br/>
2. `test_add_hosts_rbac_v2_workspace_not_found()`<br/>
   - Mock `get_rbac_workspace_by_id()` to raise 404<br/>
   - Verify endpoint returns 404<br/>
3. `test_add_hosts_feature_flag_toggle()`<br/>
   - Test flag enabled → uses RBAC v2<br/>
   - Test flag disabled → uses database<br/>

<!-- **Estimated Effort:** 2-3 days (includes implementing `get_rbac_workspace_by_id()`)<br/> -->

---

## RHINENG-17400: DELETE /groups/{group_id}/hosts/{host_id_list} (Remove Hosts)

### Status: ❌ PENDING (Missing Function)

**Endpoint:** `DELETE /api/inventory/v1/groups/{group_id}/hosts/{host_id_list}`<br/>
<!-- **File:** `api/host_group.py:75-95`<br/> -->
**Current State:** Uses database validation only, no RBAC v2 integration<br/>
**Dependencies:** Requires `get_rbac_workspace_by_id()` pending RHCLOUD-43362<br/>

### Implementation Gap

**Function:** `delete_hosts_from_group()`<br/>
- **Location:** `api/host_group.py`<br/>
- **Input Parameters:**<br/>
  - `group_id` (UUID) - Source group/workspace ID<br/>
  - `host_id_list` (list[UUID]) - Hosts to remove<br/>
  - `rbac_filter` (dict) - RBAC permissions<br/>
- **Output:** 204 No Content<br/>
- **Current Behavior:** Validates group via database (`get_group_by_id_from_db()`)<br/>
- **Required:** Feature flag check + RBAC v2 workspace validation<br/>

### Implementation Plan

<!-- **File:** `api/host_group.py:75-95`<br/> -->

1. **Add feature flag check** <!-- (line 85) -->:<br/>
   - If `FLAG_INVENTORY_KESSEL_GROUPS` enabled → call `get_rbac_workspace_by_id()`<br/>
   - If disabled → use existing database query<br/>

2. **Add workspace validation:**<br/>
   - Call `get_rbac_workspace_by_id(group_id, identity)`<br/>
   - Return 404 if workspace not found<br/>
   - Check `workspace["type"] == "ungrouped-hosts"` → return 400<br/>
   - Proceed with existing host removal logic (database)<br/>

3. **Handle ungrouped workspace check:**<br/>
   - RBAC v2: Check `workspace.get("type") == "ungrouped-hosts"`<br/>
   - Database: Check `group.ungrouped == True`<br/>

### Tests

**Existing:** Not explicitly counted (part of `tests/test_api_host_group.py`)<br/>

**Needed:** New tests<br/>
1. `test_remove_hosts_with_rbac_v2_workspace_validation()`<br/>
   - Mock workspace fetch, verify hosts removed<br/>
2. `test_remove_hosts_rbac_v2_workspace_not_found()`<br/>
   - Mock 404 from workspace fetch, verify 404 response<br/>
3. `test_remove_hosts_from_ungrouped_workspace_rbac_v2()`<br/>
   - Mock workspace with `type: "ungrouped-hosts"`, verify 400 response<br/>
4. `test_remove_hosts_feature_flag_toggle()`<br/>
   - Test both flag states<br/>

<!-- **Estimated Effort:** 1-2 days (depends on RHINENG-17399 completion) -->

---

## RHINENG-21605: GET /groups/{group_id}/hosts (List Hosts in Group)

### Status: ❌ NOT IMPLEMENTED (Endpoint Doesn't Exist)

**Endpoint:** `GET /api/inventory/v1/groups/{group_id}/hosts`<br/>
**Current State:** Endpoint not defined in swagger or code<br/>
**Dependencies:** Requires `get_rbac_workspace_by_id()` pending RHCLOUD-43362<br/>

### Implementation Gap

**Missing Components:**<br/>
1. Swagger specification for GET operation<br/>
2. API handler function<br/>
3. Repository function to query hosts by group ID<br/>

### Implementation Plan

#### Step 1: Swagger Specification

**File:** `swagger/api.spec.yaml`<br/>
**Location:** Update path `/groups/{group_id}/hosts` (currently has POST and DELETE only, needs GET)<br/>

**Add GET Operation:**<br/>
- **operationId:** `api.host_group.get_host_list_by_group`<br/>
- **Parameters:**<br/>
  - `group_id` (path, UUID) - Group/workspace ID<br/>
  - `page`, `per_page` (query) - Pagination<br/>
  - `order_by`, `order_how` (query) - Sorting<br/>
  - Standard host filters (staleness, tags, etc.)<br/>
- **Responses:**<br/>
  - 200: Paginated host list<br/>
  - 404: Group not found<br/>

#### Step 2: API Handler

**Function:** `get_host_list_by_group()`<br/>
- **Location:** `api/host_group.py` (new function)<br/>
- **Input Parameters:**<br/>
  - `group_id` (UUID) - Group/workspace ID<br/>
  - `page` (int, default=1)<br/>
  - `per_page` (int, default=100)<br/>
  - `order_by` (string, optional)<br/>
  - `order_how` (string, optional)<br/>
  - Host filters (staleness, tags, registered_with, etc.)<br/>
  - `rbac_filter` (dict)<br/>
- **Output:** `{"total": int, "count": int, "page": int, "per_page": int, "results": [...]}`<br/>

**Logic:**<br/>
1. Check `FLAG_INVENTORY_KESSEL_GROUPS`:<br/>
   - If enabled → validate workspace via `get_rbac_workspace_by_id()`<br/>
   - If disabled → validate group via database<br/>
2. Call `get_host_list_by_group_id()` repository function<br/>
3. Return paginated results<br/>

#### Phase 3: Repository Function

**Function:** `get_host_list_by_group_id()`<br/>
- **Location:** `lib/host_repository.py` (new function)<br/>
- **Input:**<br/>
  - `group_id` (UUID)<br/>
  - `org_id` (string)<br/>
  - Pagination and filter parameters<br/>
- **Output:** `(host_list: list, total: int)`<br/>
- **Query:** JOIN `hosts` with `hosts_groups` table, apply filters<br/>

#### Phase 4: Tests

**File:** `tests/test_api_host_group.py` (new tests)<br/>

**Needed Tests:**<br/>
1. `test_get_hosts_in_group_basic()
   - Create group with hosts, verify list returned<br/>
2. `test_get_hosts_in_group_pagination()`
   - Test page/per_page parameters<br/>
3. `test_get_hosts_in_group_sorting()
   - Test order_by/order_how parameters<br/>
4. `test_get_hosts_in_group_filters()`
   - Test staleness, tags, registered_with filters<br/>
5. `test_get_hosts_in_group_not_found(
   - Request non-existent group, verify 404<br/>
6. `test_get_hosts_in_group_rbac_v2_validation()`
   - Feature flag enabled, mock workspace fetch<br/>
7. `test_get_hosts_in_group_rbac_denied()`
   - Test RBAC permissions<br/>
8. `test_get_hosts_in_group_empty_group()`
   - Group exists but has no hosts<br/>

<!-- **Estimated Effort:** 3-4 days -->

---

## Core Function: get_rbac_workspace_by_id()

### Status: ❌ NOT IMPLEMENTED (Blocks 3 Tickets)

**Function:** `get_rbac_workspace_by_id()`<br/>
**Location:** `lib/middleware.py` (new function)<br/>
**Blocks:** RHINENG-17399, RHINENG-17400, RHINENG-21605<br/>

### Specification

**Input:**<br/>
- `workspace_id` (str) - UUID of workspace<br/>
- `identity` (Identity) - User identity object<br/>

**Output:**<br/>
- `dict` - Workspace object from RBAC v2 API<br/>

**Errors:**<br/>
- `ResourceNotFoundException` - Workspace not found (404)<br/>
- `HTTPException` - RBAC v2 API errors (5xx, etc.)<br/>

**Implementation Details:**<br/>
1. Build URL: `{RBAC_V2_BASE_URL}/workspaces/{workspace_id}`<br/>
2. Add headers: `{"x-rh-identity": to_auth_header(identity)}`<br/>
3. Execute GET request via `_execute_rbac_http_request()`<br/>
4. Handle 404 → raise `ResourceNotFoundException`<br/>
5. Return JSON response<br/>

**Related Functions:**
- `_get_rbac_workspace_url(workspace_id)` - Build URL (already exists)<br/>
- `_execute_rbac_http_request()` - HTTP handler (already exists)<br/>

### Tests

**File:** `tests/test_rbac_v2.py` (add new tests)<br/>

**Needed Tests:**<br/>
1. `test_get_rbac_workspace_by_id_success()`
   - Mock RBAC v2 API response, verify workspace returned<br/>
2. `test_get_rbac_workspace_by_id_not_found()`
   - Mock 404 response, verify exception raised<br/>
3. `test_get_rbac_workspace_by_id_url_construction()`
   - Verify correct URL format<br/>
4. `test_get_rbac_workspace_by_id_headers()`
   - Verify identity header included<br/>

<!-- **Estimated Effort:** 1 day -->

---

## Summary Table

| Ticket | Status | Endpoint | Blocker | Effort |
|--------|--------|----------|---------|--------|
| **RHINENG-17393** | ✅ Complete | GET /groups | Sorting (RHCLOUD-42653) | Done |
| **RHINENG-17397** | ⚠️ Blocked | GET /groups/{ids} | RHCLOUD-43362 | TBD |
| **RHINENG-17399** | ❌ Pending | POST /groups/{id}/hosts | Missing function | 2-3 days |
| **RHINENG-17400** | ❌ Pending | DELETE /groups/{id}/hosts/{ids} | Missing function | 1-2 days |
| **RHINENG-21605** | ❌ Pending | GET /groups/{id}/hosts | Missing function + endpoint | 3-4 days |

**Critical Path:**<br/>
1. Implement `get_rbac_workspace_by_id()`<br/>
2. Complete RHINENG-17399 (2-3 days)<br/>
3. Complete RHINENG-17400 (1-2 days)<br/>
4. Complete RHINENG-21605 (3-4 days)<br/>

<!-- **Total Estimated Effort:** 7-10 days -->

---

## Test Coverage Summary

### Existing Tests

| Test File | Count | Coverage |
|-----------|-------|----------|
| `tests/test_api_groups_get.py` | 13 | GET /groups endpoint |
| `tests/test_api_groups_create.py` | ~10 | POST /groups endpoint |
| `tests/test_api_groups_update.py` | ~8 | PATCH /groups endpoint |
| `tests/test_api_groups_delete.py` | ~6 | DELETE /groups endpoint |
| `tests/test_api_host_group.py` | 16+ | POST/DELETE hosts to/from groups |
| `tests/test_rbac_v2.py` | 8 | RBAC v2 integration layer |

### Tests Needed

**For `get_rbac_workspace_by_id()` (4 tests):**
- Success case, 404 case, URL construction, header validation

**For RHINENG-17399 (3 tests):**
- RBAC v2 validation success, workspace not found, feature flag toggle

**For RHINENG-17400 (4 tests):**
- RBAC v2 validation success, workspace not found, ungrouped workspace, feature flag toggle

**For RHINENG-21605 (8 tests):**
- Basic list, pagination, sorting, filters, not found, RBAC v2 validation, RBAC denied, empty group

**Total New Tests Needed:** 19 tests

__NOTE:__ Groups fixutre or helper function may need updates if one serializing groups is changed.

---

**Document End** | **Last Updated:** 2025-12-10
