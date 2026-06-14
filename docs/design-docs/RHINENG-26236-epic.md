## Epic: IQE API Client Migration — Apigen to Direct Requests

### Problem

The IQE test suite depends on auto-generated OpenAPI bindings (`iqe apigen` / `openapi-generator-cli 7.6.0`) to interact with the HBI API. This creates several problems:

1. **Regeneration overhead** — every spec change requires running `iqe apigen generate-api`, which produces ~3.7MB of generated code across two packages (`iqe_host_inventory_api/` at 1.9MB, `iqe_host_inventory_api_v7/` at 1.8MB)
2. **Abstraction mismatch** — tests interact through 3 layers: wrapper → apigen API class → urllib3. Debugging HTTP failures means tracing through generated code nobody wrote or understands
3. **Tight coupling to spec format** — generated method names like `api_group_get_group_list` are derived from operationIds. Renaming an operationId (which we just did for [V2 workspaces](https://github.com/RedHatInsights/insights-host-inventory/blob/v2-api/swagger/api_v2.spec.yaml)) breaks all call sites
4. **V2 blocker** — the V2 API spec introduces new endpoints and renames. Regenerating bindings for V2 perpetuates all the above problems. Better to migrate now

### Architecture (Current → Target)

**Current:**
```
Test → Wrapper (GroupsAPIWrapper) → Apigen (GroupsApi) → ApiClient → urllib3
                                     ↑ ~500KB generated code
```

**Target:**
```
Test → Wrapper (GroupsAPIWrapper) → requests.Session (direct HTTP)
```

The wrapper layer (`modeling/groups_api.py`, `modeling/hosts_api.py`, etc.) stays — it provides useful test helpers (wait_for_created, cleanup registration, retry logic). Only its internals change: instead of calling `self.raw_api.api_group_get_group_list(...)`, it calls `self.session.get("/api/inventory/v1/groups", params={...})`.

### Before / After

**Before (apigen):**
```python
# groups_api.py wrapper
from iqe_host_inventory_api import GroupsApi, GroupQueryOutput

@cached_property
def raw_api(self) -> GroupsApi:
    return self._host_inventory.rest_client.groups_api

def get_groups_response(self, *, name=None, per_page=None, page=None,
                        order_by=None, order_how=None, **api_kwargs):
    return self.raw_api.api_group_get_group_list(
        name=name, per_page=per_page, page=page,
        order_by=order_by, order_how=order_how, **api_kwargs,
    )
```

**After (direct requests):**
```python
# groups_api.py wrapper
def get_groups_response(self, *, name=None, per_page=None, page=None,
                        order_by=None, order_how=None):
    params = {k: v for k, v in {
        "name": name, "per_page": per_page, "page": page,
        "order_by": order_by, "order_how": order_how,
    }.items() if v is not None}

    response = self.session.get("/api/inventory/v1/groups", params=params)
    response.raise_for_status()
    return response.json()
```

### Scope

**In scope (this epic):**
- New base HTTP client/session wrapper using `requests.Session` with auth headers, retries, and base URL config
- Migrate wrapper classes directly impacted by V2 work (groups/workspaces, hosts, host-views) as proof of concept
- Return plain dicts from the wrappers instead of Pydantic model objects (tests assert on dict keys)

**Out of scope:**
- Full migration of all wrapper classes (tags, system_profile, staleness, etc.)
- Removing `iqe_host_inventory_api/` and `iqe_host_inventory_api_v7/` packages (until full migration)

### Deliverables

1. **PR 1** — Base HTTP session client + migrate a single wrapper method (e.g., `get_groups_response`) with one test passing
2. **PR 2** — Migrate remaining groups wrapper methods
3. **PR 3** — Migrate hosts wrapper methods impacted by V2
