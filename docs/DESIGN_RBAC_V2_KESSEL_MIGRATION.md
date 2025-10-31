# Design Document: Groups API Authorization Migration

## Document Information
- **Date**: October 30, 2025
- **Author**: HBI Team
- **Status**: Draft
- **Related JIRA Epic**: RHINENG-21397

## Executive Summary

This document outlines the design for migrating the Host Based Inventory (HBI) Groups API endpoints from RBAC V1 to RBAC V2 and Kessel Inventory authorization systems. The migration involves updating 10 endpoints and adding 1 new endpoint to support modern authorization infrastructure.

---

## 1. Background

### 1.1 Current State

The HBI Groups API currently uses two authorization patterns:
- **RBAC V1**: Legacy decorator `@rbac()` that calls RBAC V1 API (`/api/rbac/v1/access/`)
- **Kessel (Partial)**: Some endpoints use `@access()` decorator with Kessel integration

### 1.2 Problem Statement

1. **Inconsistent Authorization**: Mixed use of RBAC V1 and Kessel creates confusion
2. **Deprecated System**: RBAC V1 is being phased out across Red Hat platform
3. **Missing Functionality**: No endpoint exists to list hosts within a specific group
4. **Technical Debt**: Need to modernize authorization before RBAC V1 sunset

### 1.3 Goals

- Migrate all Groups API endpoints to use RBAC V2/Kessel authorization
- Maintain backward compatibility during transition
- Add missing `GET /groups/{group_id}/hosts` endpoint
- Ensure consistent authorization patterns across all endpoints

---

## 2. Authorization Systems Overview

### 2.1 RBAC V1 (Current - Legacy)

**Decorator**: `@rbac(RbacResourceType, RbacPermission, permission_base)`

**Location**: `lib/middleware.py::rbac()`

**Behavior**:
- Calls RBAC V1 API: `/api/rbac/v1/access/?application={app}`
- Returns permission list with optional resource definitions
- Supports group-level filtering via `attributeFilter`
- Passes `rbac_filter` parameter to endpoint functions

**Example**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
def get_group_list(name=None, page=1, per_page=100, rbac_filter=None):
    # rbac_filter = {"groups": ["uuid1", "uuid2"]} or None
    pass
```

### 2.2 RBAC V2 / Kessel (Target)

**Decorator**: `@access(KesselPermission, id_param="")`

**Location**: `lib/middleware.py::access()`

**Behavior**:
- Uses Kessel gRPC service for authorization checks
- Feature flag controlled: `FLAG_INVENTORY_KESSEL_PHASE_1`
- Falls back to RBAC V1 when flag is disabled
- Supports both ID-based checks and workspace filtering
- Uses `KesselResourceType` and `KesselPermission` classes

**Example**:
```python
@access(KesselResourceTypes.WORKSPACE.move_host)
def add_host_list_to_group(group_id, host_id_list, rbac_filter=None):
    # rbac_filter = {"groups": ["workspace_uuid1"]} or None
    pass
```

### 2.3 Key Differences

| Aspect | RBAC V1 | RBAC V2 / Kessel |
|--------|---------|------------------|
| API Type | REST | gRPC |
| Endpoint | `/api/rbac/v1/access/` | Kessel gRPC service |
| Feature Flag | N/A | `FLAG_INVENTORY_KESSEL_PHASE_1` |
| Resource Model | Application-based | Workspace-based |
| Permission Granularity | Coarse (read/write) | Fine-grained (view/update/move/delete) |
| Fallback | None | Falls back to RBAC V1 |

---

## 3. Endpoint Migration Plan

### 3.1 Endpoints Requiring RBAC V2 Migration

#### 3.1.1 GET /groups/{group_id_list} (RHINENG-17397)

**Current Implementation**: `api/group.py::get_groups_by_id()`

**Current Authorization**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.view, id_param="group_id_list")
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Define new `view` permission on `WorkspaceKesselResourceType`
3. Pass `group_id_list` as `id_param` for resource-specific checks
4. Maintain `rbac_filter` parameter for backward compatibility

**Implementation Notes**:
- The `group_id_list` parameter contains comma-separated UUIDs
- Kessel will check if user has `view` permission on each workspace
- If any workspace is unauthorized, return 403 Forbidden
- `rbac_filter` will contain allowed workspace IDs when filtering is needed

---

#### 3.1.2 DELETE /groups/{group_id_list} (RHINENG-17396)

**Current Implementation**: `api/group.py::delete_groups()`

**Current Authorization**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.delete, id_param="group_id_list")
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Define new `delete` permission on `WorkspaceKesselResourceType`
3. Pass `group_id_list` as `id_param`
4. Maintain existing ungrouped workspace protection logic

**Implementation Notes**:
- Must prevent deletion of ungrouped workspace
- Kessel checks deletion permission per workspace
- RBAC workspace deletion via `delete_rbac_workspace()` remains unchanged
- Handle partial failures (some workspaces authorized, others not)

---

#### 3.1.3 POST /groups (RHINENG-17394)

**Current Implementation**: `api/group.py::create_group()`

**Current Authorization**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.create)
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Define new `create` permission on `WorkspaceKesselResourceType`
3. Remove `rbac_filter` check (creation requires unfiltered permission)
4. Maintain existing logic that rejects filtered permissions

**Implementation Notes**:
- Group creation requires **unfiltered** workspace write permission
- Current code already checks: `if rbac_filter is not None: abort(403)`
- Kessel should return no filter for create operations
- Workspace ID comes from RBAC V2 after `post_rbac_workspace()` call

---

#### 3.1.4 DELETE /groups/hosts/{host_id_list} (RHINENG-17395)

**Current Implementation**: `api/group.py::delete_hosts_from_different_groups()`

**Current Authorization**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.move_host)
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Use existing `move_host` permission (hosts are moved to ungrouped)
3. No `id_param` needed (hosts determine which groups are affected)
4. Maintain dynamic group ID collection logic

**Implementation Notes**:
- Function determines affected groups by looking up each host
- Calls `rbac_group_id_check()` after collecting group IDs
- Moving hosts out of groups = moving them to ungrouped workspace
- Requires write permission on source workspaces

---

#### 3.1.5 PATCH /groups/{group_id} (RHINENG-17398)

**Current Implementation**: `api/group.py::patch_group_by_id()`

**Current Authorization**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.update, id_param="group_id")
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Define new `update` permission on `WorkspaceKesselResourceType`
3. Pass `group_id` as `id_param`
4. Maintain ungrouped workspace rename protection

**Implementation Notes**:
- Patching includes renaming group and/or replacing host list
- Renaming calls `patch_rbac_workspace()` to update RBAC V2
- Replacing host list triggers host update events
- Cannot rename ungrouped workspace

---

#### 3.1.6 POST /groups/{group_id}/hosts (RHINENG-17399)

**Current Implementation**: `api/host_group.py::add_host_list_to_group()`

**Current Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.move_host)
```

**Target Authorization**: ✅ **Already using RBAC V2/Kessel**

**Changes Required**: **NONE** - Already migrated

**Verification Needed**:
- Confirm `move_host` permission is correctly defined
- Ensure fallback to RBAC V1 works when feature flag is off
- Test with both feature flag states

---

#### 3.1.7 DELETE /groups/{group_id}/hosts/{host_id_list} (RHINENG-17400)

**Current Implementation**: `api/host_group.py::delete_hosts_from_group()`

**Current Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.move_host)
```

**Target Authorization**: ✅ **Already using RBAC V2/Kessel**

**Changes Required**: **NONE** - Already migrated

**Verification Needed**:
- Confirm ungrouped workspace protection works
- Test permission checks with feature flag on/off
- Validate hosts are moved to ungrouped workspace

---

### 3.2 Endpoints Requiring Kessel Migration

#### 3.2.1 GET /groups (RHINENG-17393)

**Current Implementation**: `api/group.py::get_group_list()`

**Current Authorization**:
```python
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.view)
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Use `view` permission on `WorkspaceKesselResourceType`
3. No `id_param` (listing operation)
4. Kessel will return filtered workspace IDs via `rbac_filter`

**Implementation Notes**:
- Kessel calls `ListAllowedWorkspaces()` to get accessible workspace IDs
- `rbac_filter = {"groups": [workspace_ids]}` passed to query function
- Database query filters by workspace IDs in `rbac_filter`
- Supports `group_type` parameter (standard, ungrouped-hosts, all)

---

#### 3.2.2 GET /resource-types/inventory-groups (RHINENG-17534)

**Current Implementation**: `api/resource_type.py::get_resource_type_groups_list()`

**Current Authorization**:
```python
@rbac(RbacResourceType.ALL, RbacPermission.ADMIN, "rbac")
```

**Target Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.view)
```

**Changes Required**:
1. Replace `@rbac` decorator with `@access`
2. Change from ADMIN permission to workspace view permission
3. Update permission base from "rbac" to "inventory"
4. Maintain RBAC-specific response format

**Implementation Notes**:
- This endpoint is used by RBAC service for resource type discovery
- Response format must match RBAC expectations
- Currently requires admin permission, should use workspace view
- Returns groups in paginated resource-types format

---

### 3.3 New Endpoint

#### 3.3.1 GET /groups/{group_id}/hosts (RHINENG-21605)

**Purpose**: Retrieve all hosts belonging to a specific group

**Authorization**:
```python
@access(KesselResourceTypes.WORKSPACE.view, id_param="group_id")
```

**API Specification**:

**Path**: `/groups/{group_id}/hosts`

**Method**: `GET`

**Parameters**:
- `group_id` (path, required): UUID of the group
- `page` (query, optional): Page number (default: 1)
- `per_page` (query, optional): Items per page (default: 100, max: 100)
- `order_by` (query, optional): Sort field (display_name, updated, operating_system)
- `order_how` (query, optional): Sort direction (ASC, DESC)
- `staleness` (query, optional): Filter by staleness (fresh, stale, stale_warning)
- `tags` (query, optional): Filter by tags
- `filter` (query, optional): System profile filters
- `fields` (query, optional): Sparse fieldsets for system_profile

**Response**: `HostQueryOutput` (same as `GET /hosts`)

**Implementation**:

**File**: `api/host_group.py`

```python
@api_operation
@access(KesselResourceTypes.WORKSPACE.view, id_param="group_id")
@metrics.api_request_time.time()
def get_hosts_in_group(
    group_id,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    staleness=None,
    tags=None,
    filter=None,
    fields=None,
    rbac_filter=None,
):
    """
    Get all hosts belonging to a specific group.
    
    Required permissions: inventory:groups:read (via workspace view)
    """
    from api.host_query import build_paginated_host_list_response
    from lib.host_repository import get_host_list_by_group_id
    
    # Verify user has access to this group
    rbac_group_id_check(rbac_filter, {group_id})
    
    identity = get_current_identity()
    
    # Verify group exists and belongs to user's org
    group = get_group_by_id_from_db(group_id, identity.org_id)
    if not group:
        abort(HTTPStatus.NOT_FOUND, "Group not found.")
    
    try:
        # Get hosts in this group with filters
        host_list, total = get_host_list_by_group_id(
            group_id=group_id,
            org_id=identity.org_id,
            page=page,
            per_page=per_page,
            order_by=order_by,
            order_how=order_how,
            staleness=staleness,
            tags=tags,
            filter=filter,
            fields=fields,
        )
    except ValueError as e:
        logger.exception(f"Error retrieving hosts for group {group_id}")
        abort(HTTPStatus.BAD_REQUEST, str(e))
    
    logger.info(f"Retrieved {len(host_list)} hosts for group {group_id}")
    
    return flask_json_response(
        build_paginated_host_list_response(total, page, per_page, host_list)
    )
```

**Repository Function**:

**File**: `lib/host_repository.py`

```python
def get_host_list_by_group_id(
    group_id: str,
    org_id: str,
    page: int = 1,
    per_page: int = 100,
    order_by: str = None,
    order_how: str = None,
    staleness: list[str] = None,
    tags: list = None,
    filter: dict = None,
    fields: dict = None,
) -> tuple[list[Host], int]:
    """
    Get paginated list of hosts belonging to a specific group.
    
    Args:
        group_id: UUID of the group
        org_id: Organization ID
        page: Page number
        per_page: Items per page
        order_by: Field to sort by
        order_how: Sort direction (ASC/DESC)
        staleness: Staleness filter
        tags: Tag filters
        filter: System profile filters
        fields: Sparse fieldsets
    
    Returns:
        Tuple of (host_list, total_count)
    """
    from api.filtering.db_filters import build_host_filters
    from api.staleness_query import get_staleness_obj
    
    # Start with base query for hosts in this group
    query = (
        db.session.query(Host)
        .join(HostGroupAssoc, Host.id == HostGroupAssoc.host_id)
        .filter(
            HostGroupAssoc.group_id == group_id,
            Host.org_id == org_id
        )
    )
    
    # Apply staleness filter
    staleness_obj = get_staleness_obj(org_id)
    if staleness:
        query = apply_staleness_filter(query, staleness, staleness_obj)
    else:
        # Default: exclude culled hosts
        query = query.filter(Host.stale_timestamp > func.now())
    
    # Apply tag filters
    if tags:
        query = apply_tag_filters(query, tags)
    
    # Apply system profile filters
    if filter:
        query = build_host_filters(query, filter)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply ordering
    if order_by:
        query = apply_ordering(query, order_by, order_how)
    else:
        query = query.order_by(Host.display_name.asc())
    
    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    # Execute query
    host_list = query.all()
    
    return host_list, total
```

**Swagger Specification**:

**File**: `swagger/api.spec.yaml`

```yaml
'/groups/{group_id}/hosts':
  get:
    operationId: api.host_group.get_hosts_in_group
    tags:
      - groups
    summary: Get hosts in a specific group
    description: >-
      Retrieve all hosts belonging to a specific group with optional filtering.
      <br /><br />
      Required permissions: inventory:groups:read
    security:
      - ApiKeyAuth: []
    parameters:
      - $ref: '#/components/parameters/groupId'
      - $ref: '#/components/parameters/perPageParam'
      - $ref: '#/components/parameters/pageParam'
      - $ref: '#/components/parameters/hostOrderByParam'
      - $ref: '#/components/parameters/hostOrderHowParam'
      - $ref: '#/components/parameters/stalenessParam'
      - $ref: '#/components/parameters/tagsParam'
      - $ref: '#/components/parameters/filter_param'
      - $ref: '#/components/parameters/fields_param'
    responses:
      '200':
        description: Successfully retrieved hosts in group.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/HostQueryOutput'
      '400':
        description: Invalid request.
      '404':
        description: Group not found.
```

---

## 4. Implementation Details

### 4.1 New Kessel Permissions Required

**File**: `app/auth/rbac.py`

Add the following permissions to `WorkspaceKesselResourceType`:

```python
class WorkspaceKesselResourceType(KesselResourceType):
    def __init__(self) -> None:
        super().__init__("rbac", "workspace", RbacResourceType.GROUPS, "inventory")
        
        # Existing
        self.move_host = KesselPermission(
            self, "inventory_host_move", "inventory_host_move", RbacPermission.WRITE
        )
        
        # New permissions needed
        self.view = KesselPermission(
            self, "inventory_workspace_view", "view", RbacPermission.READ
        )
        self.create = KesselPermission(
            self, "inventory_workspace_create", "create", RbacPermission.WRITE
        )
        self.update = KesselPermission(
            self, "inventory_workspace_update", "update", RbacPermission.WRITE
        )
        self.delete = KesselPermission(
            self, "inventory_workspace_delete", "delete", RbacPermission.WRITE
        )
```

### 4.2 Feature Flag Strategy

**Flag**: `FLAG_INVENTORY_KESSEL_PHASE_1`

**Behavior**:
- When `True`: Use Kessel gRPC authorization
- When `False`: Fall back to RBAC V1 REST API
- Controlled via Unleash feature flag system

**Rollout Plan**:
1. **Phase 1**: Deploy code with flag OFF (default to RBAC V1)
2. **Phase 2**: Enable flag in DEV environment, test thoroughly
3. **Phase 3**: Enable flag in STAGE environment, run full IQE test suite
4. **Phase 4**: Gradual rollout in PROD (10% → 50% → 100%)
5. **Phase 5**: Remove RBAC V1 fallback code after successful migration

### 4.3 Backward Compatibility

All migrated endpoints must:
1. Accept `rbac_filter` parameter (even if not used)
2. Call `rbac_group_id_check()` when group IDs are involved
3. Return same response format as before
4. Maintain same error codes and messages
5. Support both authorization systems via feature flag

### 4.4 Error Handling

**Authorization Failures**:
- HTTP 403 Forbidden when user lacks permission
- Log authorization denials for audit trail
- Include helpful error messages

**Kessel Service Failures**:
- Fall back to RBAC V1 if Kessel is unavailable
- Log gRPC errors with appropriate severity
- Return HTTP 503 if both systems are unavailable

**Validation Failures**:
- HTTP 400 Bad Request for invalid input
- HTTP 404 Not Found for non-existent resources
- Maintain existing validation logic

---

## 5. Testing Strategy

### 5.1 Unit Tests

**File**: `tests/test_api_group.py`, `tests/test_api_host_group.py`

For each migrated endpoint:
1. Test with feature flag ON (Kessel)
2. Test with feature flag OFF (RBAC V1)
3. Test authorization success cases
4. Test authorization failure cases
5. Test with filtered permissions
6. Test with unfiltered permissions
7. Test Kessel service unavailability
8. Test backward compatibility

**New Endpoint Tests**:
```python
def test_get_hosts_in_group_success(self, api_get, mocker):
    """Test successful retrieval of hosts in a group."""
    # Mock Kessel authorization
    mocker.patch("lib.middleware.get_kessel_client")
    mocker.patch("lib.middleware.get_kessel_filter", return_value=(True, None))
    
    # Create test data
    group_id = str(uuid.uuid4())
    # ... create group and hosts ...
    
    response = api_get(f"/groups/{group_id}/hosts")
    
    assert response.status_code == 200
    assert response.json()["total"] == 5
    assert len(response.json()["results"]) == 5

def test_get_hosts_in_group_unauthorized(self, api_get, mocker):
    """Test unauthorized access to group hosts."""
    mocker.patch("lib.middleware.get_kessel_filter", return_value=(False, None))
    
    group_id = str(uuid.uuid4())
    response = api_get(f"/groups/{group_id}/hosts")
    
    assert response.status_code == 403

def test_get_hosts_in_group_with_filters(self, api_get, mocker):
    """Test host retrieval with staleness and tag filters."""
    # Test with staleness=fresh, tags, system profile filters
    pass
```

### 5.2 Integration Tests

**IQE Test Suite**: `iqe-host-inventory-plugin`

1. Test all group endpoints with RBAC V2 permissions
2. Test with various permission combinations
3. Test with resource-specific filters
4. Test new `GET /groups/{group_id}/hosts` endpoint
5. Test with both feature flag states
6. Test permission inheritance and workspace hierarchy

### 5.3 Performance Tests

1. **Kessel Response Time**: Measure gRPC call latency
2. **Fallback Performance**: Ensure RBAC V1 fallback doesn't degrade performance
3. **Bulk Operations**: Test with large group ID lists
4. **Concurrent Requests**: Test under load with multiple users

### 5.4 Manual Testing Checklist

- [ ] All endpoints work with Kessel authorization
- [ ] All endpoints fall back to RBAC V1 correctly
- [ ] New endpoint returns correct host list
- [ ] Filtered permissions work as expected
- [ ] Ungrouped workspace protection works
- [ ] Error messages are clear and helpful
- [ ] Swagger UI documentation is accurate
- [ ] Audit logs capture authorization events

---

## 6. Migration Sequence

### Phase 1: Preparation (Week 1)
1. Add new Kessel permissions to `WorkspaceKesselResourceType`
2. Implement `get_hosts_in_group()` endpoint
3. Add repository function `get_host_list_by_group_id()`
4. Update Swagger specification
5. Write unit tests for all changes

### Phase 2: Endpoint Migration (Week 2)
1. Migrate `GET /groups` (RHINENG-17393)
2. Migrate `GET /groups/{group_id_list}` (RHINENG-17397)
3. Migrate `POST /groups` (RHINENG-17394)
4. Migrate `PATCH /groups/{group_id}` (RHINENG-17398)
5. Update unit tests for each endpoint

### Phase 3: Endpoint Migration Continued (Week 3)
1. Migrate `DELETE /groups/{group_id_list}` (RHINENG-17396)
2. Migrate `DELETE /groups/hosts/{host_id_list}` (RHINENG-17395)
3. Migrate `GET /resource-types/inventory-groups` (RHINENG-17534)
4. Verify already-migrated endpoints (RHINENG-17399, RHINENG-17400)
5. Complete unit test coverage

### Phase 4: Testing (Week 4)
1. Run full unit test suite
2. Deploy to DEV environment with feature flag OFF
3. Enable feature flag in DEV
4. Run integration tests in DEV
5. Performance testing

### Phase 5: Staging Deployment (Week 5)
1. Deploy to STAGE environment
2. Enable feature flag in STAGE
3. Run full IQE test suite
4. Manual testing with QE team
5. Load testing

### Phase 6: Production Rollout (Week 6-7)
1. Deploy to PROD with feature flag OFF
2. Enable flag for 10% of traffic
3. Monitor metrics and error rates
4. Gradual rollout: 25% → 50% → 100%
5. Monitor for 1 week at 100%

### Phase 7: Cleanup (Week 8)
1. Remove RBAC V1 fallback code
2. Remove feature flag checks
3. Update documentation
4. Archive JIRA tickets

---

## 7. Rollback Plan

### Immediate Rollback
If critical issues are discovered:
1. Disable `FLAG_INVENTORY_KESSEL_PHASE_1` feature flag
2. System automatically falls back to RBAC V1
3. No code deployment required

### Code Rollback
If feature flag rollback is insufficient:
1. Revert deployment to previous version
2. Restore RBAC V1 decorators
3. Deploy hotfix if necessary

### Rollback Triggers
- Authorization failures > 5% of requests
- Kessel service unavailability > 10 minutes
- Performance degradation > 50%
- Critical security vulnerability discovered

---

## 8. Monitoring and Observability

### 8.1 Metrics

**Prometheus Metrics**:
```python
# Authorization metrics
kessel_authorization_requests_total = Counter(
    "kessel_authorization_requests_total",
    "Total Kessel authorization requests",
    ["endpoint", "permission", "result"]
)

kessel_authorization_duration_seconds = Histogram(
    "kessel_authorization_duration_seconds",
    "Kessel authorization request duration",
    ["endpoint", "permission"]
)

rbac_v1_fallback_total = Counter(
    "rbac_v1_fallback_total",
    "Total fallbacks to RBAC V1",
    ["endpoint", "reason"]
)
```

### 8.2 Logging

**Authorization Events**:
```python
logger.info(
    "Kessel authorization check",
    extra={
        "endpoint": endpoint_name,
        "permission": permission_name,
        "resource_ids": resource_ids,
        "result": "allowed" | "denied",
        "duration_ms": duration,
    }
)
```

**Fallback Events**:
```python
logger.warning(
    "Falling back to RBAC V1",
    extra={
        "endpoint": endpoint_name,
        "reason": "kessel_unavailable" | "feature_flag_off",
        "kessel_error": error_message,
    }
)
```

### 8.3 Alerts

**Critical Alerts**:
- Kessel service unavailable > 5 minutes
- Authorization failure rate > 10%
- RBAC V1 fallback rate > 50%

**Warning Alerts**:
- Kessel response time > 1 second (p95)
- Authorization denied rate increased > 50%
- Feature flag toggle events

### 8.4 Dashboards

**Grafana Dashboard Panels**:
1. Authorization request rate (by endpoint)
2. Authorization success/failure ratio
3. Kessel response time (p50, p95, p99)
4. RBAC V1 fallback rate
5. Error rate by authorization system
6. Feature flag status

---

## 9. Security Considerations

### 9.1 Permission Model

**Workspace Permissions**:
- `view`: Read workspace metadata and list hosts
- `create`: Create new workspaces (groups)
- `update`: Modify workspace name and settings
- `delete`: Delete workspaces
- `move_host`: Add/remove hosts from workspace

**Permission Hierarchy**:
- Admin permission (`*`) grants all workspace permissions
- Write permission grants update, delete, and move_host
- Read permission grants view only

### 9.2 Authorization Bypass Prevention

**Safeguards**:
1. Never bypass authorization in production
2. `bypass_rbac` config only for local development
3. Always validate `rbac_filter` results
4. Log all authorization decisions
5. Audit trail for permission changes

### 9.3 Data Isolation

**Org ID Enforcement**:
- All queries filter by `org_id`
- Authorization checks include org context
- Cross-org access strictly prohibited
- Workspace IDs are org-scoped

### 9.4 Audit Requirements

**Audit Log Fields**:
- User identity (user_id, org_id)
- Requested action (endpoint, method)
- Resource IDs (group_id, host_id)
- Authorization result (allowed/denied)
- Timestamp
- Request ID for tracing

---

## 10. Documentation Updates

### 10.1 API Documentation

**Files to Update**:
- `swagger/api.spec.yaml` - Add new endpoint, update descriptions
- `docs/index.md` - Document new endpoint and authorization changes
- `README.md` - Update RBAC section with V2 information

**New Endpoint Documentation**:
```markdown
### GET /groups/{group_id}/hosts

Retrieve all hosts belonging to a specific group.

**Required Permissions**: `inventory:groups:read`

**Parameters**:
- `group_id` (path): UUID of the group
- `page`, `per_page`: Pagination
- `order_by`, `order_how`: Sorting
- `staleness`: Filter by host staleness
- `tags`: Filter by host tags
- `filter`: System profile filters

**Response**: Paginated list of hosts (same format as GET /hosts)

**Example**:
```bash
curl -H "x-rh-identity: $IDENTITY" \
  https://console.redhat.com/api/inventory/v1/groups/550e8400-e29b-41d4-a716-446655440000/hosts?per_page=50
```
```

### 10.2 Internal Documentation

**Files to Update**:
- `CLAUDE.md` - Update authorization patterns
- `docs/architecture.md` - Document RBAC V2 integration
- `docs/pull_request_template.md` - Add RBAC V2 testing checklist

### 10.3 Developer Guide

**New Section**: "Authorization with RBAC V2 and Kessel"

```markdown
## Authorization with RBAC V2 and Kessel

### Using the @access Decorator

For new endpoints or migrated endpoints, use the `@access` decorator:

```python
from app.auth.rbac import KesselResourceTypes
from lib.middleware import access

@api_operation
@access(KesselResourceTypes.WORKSPACE.view, id_param="group_id")
def my_endpoint(group_id, rbac_filter=None):
    # Endpoint implementation
    pass
```

### Permission Types

- **view**: Read-only access to resources
- **create**: Create new resources
- **update**: Modify existing resources
- **delete**: Delete resources
- **move_host**: Move hosts between workspaces

### Feature Flag

The system uses `FLAG_INVENTORY_KESSEL_PHASE_1` to control authorization:
- When enabled: Uses Kessel gRPC
- When disabled: Falls back to RBAC V1

### Testing Authorization

```python
def test_my_endpoint_authorized(mocker):
    mocker.patch("lib.middleware.get_kessel_filter", return_value=(True, None))
    # Test authorized access

def test_my_endpoint_unauthorized(mocker):
    mocker.patch("lib.middleware.get_kessel_filter", return_value=(False, None))
    # Test unauthorized access
```
```

---

## 11. Dependencies and Prerequisites

### 11.1 External Dependencies

**Services**:
- Kessel gRPC service (inventory service)
- RBAC V2 service (workspace management)
- Unleash feature flag service

**Libraries**:
- `kessel-sdk` >= 2.0.0 (already in Pipfile)
- `grpc` and `grpcio` (already installed)
- `googleapis-common-protos` (already installed)

### 11.2 Configuration

**Environment Variables**:
```bash
# Kessel configuration
KESSEL_TARGET_URL=kessel-inventory:9000
KESSEL_TIMEOUT=10.0

# RBAC V2 configuration
RBAC_ENDPOINT=http://rbac-service:8080
RBAC_TIMEOUT=5

# Feature flags
UNLEASH_URL=http://unleash:4242/api
UNLEASH_TOKEN=<token>
```

### 11.3 Database Changes

**No database migrations required** for this work.

All changes are at the API authorization layer only.

---

## 12. Success Criteria

### 12.1 Functional Requirements

- [ ] All 10 endpoints migrated to RBAC V2/Kessel
- [ ] New `GET /groups/{group_id}/hosts` endpoint implemented
- [ ] Feature flag controls authorization system
- [ ] Backward compatibility maintained
- [ ] All unit tests passing
- [ ] All integration tests passing

### 12.2 Performance Requirements

- [ ] Kessel authorization latency < 100ms (p95)
- [ ] No performance degradation vs RBAC V1
- [ ] Fallback to RBAC V1 works within 1 second
- [ ] Endpoint response times unchanged

### 12.3 Quality Requirements

- [ ] Code coverage > 90% for new code
- [ ] No new linter errors
- [ ] All pre-commit hooks passing
- [ ] Documentation complete and accurate
- [ ] Security review completed

### 12.4 Operational Requirements

- [ ] Monitoring dashboards created
- [ ] Alerts configured
- [ ] Runbook documented
- [ ] Rollback plan tested
- [ ] On-call team trained

---

## 13. Risks and Mitigation

### 13.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Kessel service instability | High | Medium | Fallback to RBAC V1, monitoring |
| Permission model mismatch | High | Low | Thorough testing, gradual rollout |
| Performance degradation | Medium | Low | Performance testing, optimization |
| Feature flag failure | High | Low | Manual override capability |

### 13.2 Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Authorization failures | High | Medium | Comprehensive testing, rollback plan |
| Incomplete migration | Medium | Low | Checklist, code review |
| Documentation gaps | Low | Medium | Documentation review process |
| Training gaps | Medium | Low | Team training sessions |

### 13.3 Business Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| User access disruption | High | Low | Gradual rollout, communication |
| RBAC V1 sunset deadline | Medium | Medium | Prioritize migration, track progress |
| Customer complaints | Medium | Low | Clear communication, support readiness |

---

## 14. Open Questions

1. **Q**: Should `GET /groups/{group_id}/hosts` support all host filters?
   **A**: Yes, maintain consistency with `GET /hosts` endpoint

2. **Q**: What happens if Kessel and RBAC V1 return different permissions?
   **A**: Kessel takes precedence when feature flag is enabled

3. **Q**: Should we log all authorization decisions?
   **A**: Log denials always, log approvals at DEBUG level

4. **Q**: How do we handle partial authorization (some groups allowed, others not)?
   **A**: For bulk operations, return 403 if ANY resource is unauthorized

5. **Q**: Should we remove RBAC V1 code immediately after migration?
   **A**: No, keep fallback for 1 release cycle, then remove

---

## 15. Appendix

### 15.1 JIRA Tickets Summary

| Ticket | Endpoint | Type | Status |
|--------|----------|------|--------|
| RHINENG-17393 | GET /groups | Kessel | NEW |
| RHINENG-17397 | GET /groups/{group_id_list} | RBAC V2 | NEW |
| RHINENG-17534 | GET /resource-types/inventory-groups | Kessel | NEW |
| RHINENG-17396 | DELETE /groups/{group_id_list} | RBAC V2 | NEW |
| RHINENG-21605 | GET /groups/{group_id}/hosts | New Endpoint | NEW |
| RHINENG-17394 | POST /groups | RBAC V2 | NEW |
| RHINENG-17395 | DELETE /groups/hosts/{host_id_list} | RBAC V2 | NEW |
| RHINENG-17398 | PATCH /groups/{group_id} | RBAC V2 | NEW |
| RHINENG-17399 | POST /groups/{group_id}/hosts | Already Done | NEW |
| RHINENG-17400 | DELETE /groups/{group_id}/hosts/{host_id_list} | Already Done | NEW |

### 15.2 Code References

**Key Files**:
- `api/group.py` - Group management endpoints
- `api/host_group.py` - Host-group association endpoints
- `api/resource_type.py` - RBAC resource type endpoints
- `lib/middleware.py` - Authorization decorators
- `lib/kessel.py` - Kessel client implementation
- `lib/group_repository.py` - Group data access
- `app/auth/rbac.py` - Permission definitions
- `swagger/api.spec.yaml` - API specification

### 15.3 Related Documentation

- [RBAC V2 Documentation](https://internal.redhat.com/rbac-v2)
- [Kessel Inventory Service](https://internal.redhat.com/kessel)
- [HBI Architecture](./architecture.md)
- [HBI API Documentation](https://console.redhat.com/docs/api/inventory/v1)

### 15.4 Contact Information

**Team**: @team-inventory-dev
**Slack Channel**: #team-insights-inventory
**On-Call**: PagerDuty - Insights Inventory

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-30 | HBI Team | Initial design document |

---

**END OF DOCUMENT**

