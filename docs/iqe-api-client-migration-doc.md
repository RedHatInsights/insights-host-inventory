## IQE API Client Migration: Apigen to app.http_client

### Problem

The IQE test suite depends on auto-generated OpenAPI bindings (`iqe apigen` / `openapi-generator-cli 7.6.0`) to interact with the HBI API. This creates several problems:

1. **Regeneration overhead** — every spec change requires running `iqe apigen generate-api`, which produces ~3.7MB of generated code across two packages (`iqe_host_inventory_api/` at 1.9MB, `iqe_host_inventory_api_v7/` at 1.8MB)
2. **Abstraction mismatch** — tests interact through 3 layers: wrapper → apigen API class → urllib3. Debugging HTTP failures means tracing through generated code nobody wrote or understands
3. **Tight coupling to spec format** — generated method names like `api_group_get_group_list` are derived from operationIds. Renaming an operationId (which we just did for [V2 workspaces](https://github.com/RedHatInsights/insights-host-inventory/blob/v2-api/swagger/api_v2.spec.yaml)) breaks all call sites
4. **V2 blocker** — the V2 API spec introduces new endpoints and renames. Regenerating bindings for V2 perpetuates all the above problems. Better to migrate now

### Solution

Replace the auto-generated apigen bindings with a lightweight `BaseAPIWrapper` that uses IQE's built-in `app.http_client` (`RobustSession`) for direct HTTP calls. The wrapper reads protocol, hostname, and port from `app.host_inventory.config` and combines them with the versioned API path, so individual wrappers only need to specify the resource path (e.g., `/workspaces`). V2 endpoints migrate first as a proof of concept; V1 endpoints remain on apigen until cross-team coordination is complete.

### Architecture (Current → Target)

**Current:**
```
Test → Wrapper (GroupsAPIWrapper) → Apigen (GroupsApi) → ApiClient → urllib3
                                     ↑ ~3.7MB generated code
```

**Target:**
```
Test → Wrapper (GroupsAPIWrapper) → app.http_client (IQE's RobustSession)
```

The existing V1 wrapper layer (`modeling/groups_api.py`, `modeling/hosts_api.py`, etc.) stays unchanged and continues to use the apigen bindings. New V2 endpoint wrappers will use IQE's `app.http_client` (a `RobustSession` that already handles auth and config) with a URL helper that prepends the versioned base path.

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

**After (using `app.http_client`):**
```python
# base wrapper — builds full URL from IQE plugin config + versioned API path
class BaseAPIWrapper:
    def __init__(self, app, api_version="v2"):
        self._app = app
        # protocol, hostname, and port come from the IQE plugin config so the
        # wrapper works across ephemeral, stage, and prod without hardcoding
        inv_conf = app.host_inventory.config.get("service_objects").get("api").get("config")
        base_url = f"{inv_conf.get('scheme')}://{inv_conf.get('hostname')}:{inv_conf.get('port')}"
        self._base_path = f"{base_url}/api/inventory/{api_version}"

    @property
    def client(self):
        return self._app.http_client

    def get(self, path, **kwargs):
        return self.client.get(f"{self._base_path}{path}", **kwargs)

# workspaces_api.py wrapper
def get_workspaces_response(self, *, name=None, per_page=None, page=None,
                        order_by=None, order_how=None):
    params = {k: v for k, v in {
        "name": name, "per_page": per_page, "page": page,
        "order_by": order_by, "order_how": order_how,
    }.items() if v is not None}

    response = self.get("/workspaces", params=params)
    response.raise_for_status()
    return response.json()
```

### Scope

**In scope (this epic):**
- Base wrapper using IQE's `app.http_client` (`RobustSession`) with a URL helper for versioned path construction
- Migrate **only new V2 endpoints** (host-views, and any new endpoints under `/api/inventory/v2/...`) as proof of concept
- Return plain dicts from the new V2 wrappers (tests assert on dict keys)

### Phase 1 Deliverables

1. **PR 1** — Base wrapper using `app.http_client` with URL helper + migrate a single V2 endpoint (e.g., host-views) with one test passing
2. **PR 2** — Migrate remaining new V2 endpoints

### Future Phases

**Phase 2: Identify external dependents and coordinate with other teams**

Some IQE plugins import our wrapper classes (`hosts_api.py`, `groups_api.py`, `kafka_interactions.py`, etc.) directly, not just the auto-generated bindings. Changing the return types of those wrappers from auto-generated objects to plain dicts would break those plugins. This coordination must happen before we can safely change anything in our wrappers.

Steps:
- Identify all IQE plugins that import or depend on our wrapper classes (`hosts_api.py`, `groups_api.py`, `kafka_interactions.py`, etc.)
- For each dependent plugin, work with the owning team to either:
  - migrate their code to use iqe-bindings directly (removing the dependency on our wrappers), or
  - agree on a coordinated merge where all callers are updated to expect plain dicts at the same time
- Do not proceed to Phase 3 until all external dependencies on our wrappers are resolved

Outcome: no external IQE plugin depends on our internal wrappers; we are free to change wrapper return types without breaking other teams.

**Phase 3: Migrate V1 wrappers and remove generated packages**

Once no external plugin depends on our wrappers, migrate the existing V1 wrapper classes (`hosts_api.py`, `groups_api.py`, tags, system_profile, staleness, etc.) to use `BaseAPIWrapper` with `api_version="v1"` and return plain dicts. Then remove the generated packages.

**Do not remove the generated packages until Phase 2 is fully complete.**

Outcome: all HBI IQE wrappers use `app.http_client` directly; `iqe_host_inventory_api/` and `iqe_host_inventory_api_v7/` packages are removed; full migration complete.
