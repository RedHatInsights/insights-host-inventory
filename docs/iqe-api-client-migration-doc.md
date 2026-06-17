## IQE API Client Migration: Apigen to app.http_client

### Problem

The IQE test suite depends on auto-generated OpenAPI bindings (`iqe apigen` / `openapi-generator-cli 7.6.0`) to interact with the HBI API. This creates several problems:

1. **Regeneration overhead** — every spec change requires running `iqe apigen generate-api`, which produces ~3.7MB of generated code across two packages (`iqe_host_inventory_api/` at 1.9MB, `iqe_host_inventory_api_v7/` at 1.8MB)
2. **Abstraction mismatch** — tests interact through 3 layers: wrapper → apigen API class → urllib3. Debugging HTTP failures means tracing through generated code nobody wrote or understands
3. **Tight coupling to spec format** — generated method names like `api_group_get_group_list` are derived from operationIds. Renaming an operationId breaks all call sites
4. **Future V2 cost** — the V2 API spec will introduce new endpoints and renames. Regenerating bindings for V2 perpetuates all the above problems. Establishing the new pattern now avoids paying that cost later

### Solution

Replace the auto-generated apigen bindings with a lightweight `BaseAPIWrapper` that uses IQE's built-in `app.http_client` (`RobustSession`) for direct HTTP calls. The wrapper reads protocol, hostname, and port from `app.host_inventory.config` and combines them with the versioned API path, so individual wrappers only need to specify the resource path (e.g., `/hosts`).

Migration is **incremental and safe**: individual wrappers are migrated one at a time while the apigen packages remain installed. The public interface of each wrapper (method names and parameters) stays unchanged, so tests and external callers are not broken.

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
    def __init__(self, app, api_version="v1"):
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

# groups_api.py wrapper — same public interface, apigen removed internally
def get_groups_response(self, *, name=None, per_page=None, page=None,
                        order_by=None, order_how=None):
    params = {k: v for k, v in {
        "name": name, "per_page": per_page, "page": page,
        "order_by": order_by, "order_how": order_how,
    }.items() if v is not None}

    response = self.get("/groups", params=params)
    response.raise_for_status()
    return response.json()
```

### Phase 1: Proof of Concept — Migrate a small set of V1 endpoints

Establish the pattern using existing, live V1 endpoints. This is immediately testable and unblocks the migration without waiting for V2 to be deployed.

**Deliverables:**

1. **PR 1** — Introduce `BaseAPIWrapper` using `app.http_client` with the URL helper. Migrate a single V1 endpoint (e.g., `GET /groups`) as proof of concept, with one test passing end-to-end. The apigen packages remain installed; only this one wrapper changes internally.
2. **PR 2** — Migrate a small additional set of V1 wrappers (e.g., `GET /hosts`, `GET /tags`) to validate the pattern across different resource types.

**What stays unchanged:**
- All other V1 wrappers continue to use apigen — no disruption to tests or external callers
- The apigen packages (`iqe_host_inventory_api/`, `iqe_host_inventory_api_v7/`) remain installed throughout this phase
- Return types are plain dicts, compatible with existing test assertions

### Phase 2: Identify external dependents and coordinate with other teams

Some IQE plugins import our wrapper classes (`hosts_api.py`, `groups_api.py`, `kafka_interactions.py`, etc.) directly. Changing return types from apigen-generated objects to plain dicts would break those plugins. This coordination must happen before we migrate the remaining wrappers.

Steps:
- Identify all IQE plugins that import or depend on our wrapper classes
- For each dependent plugin, work with the owning team to either:
  - migrate their code to use iqe-bindings directly (removing the dependency on our wrappers), or
  - agree on a coordinated merge where all callers are updated to expect plain dicts at the same time
- Do not proceed to Phase 3 until all external dependencies on our wrappers are resolved

Outcome: no external IQE plugin depends on our internal wrappers; we are free to change all remaining wrapper return types without breaking other teams.

### Phase 3: Complete V1 migration, add V2 wrappers, remove generated packages

Once external dependencies are resolved:

- Migrate all remaining V1 wrapper classes (`hosts_api.py`, `groups_api.py`, tags, system_profile, staleness, etc.) to use `BaseAPIWrapper` with `api_version="v1"` and return plain dicts.
- As V2 endpoints go live, write their wrappers using `BaseAPIWrapper` with `api_version="v2"` from day one — no apigen involvement.
- Remove the generated packages (`iqe_host_inventory_api/`, `iqe_host_inventory_api_v7/`) once all wrappers are migrated.

**Do not remove the generated packages until all wrappers have been migrated off apigen.**

Outcome: all HBI IQE wrappers use `app.http_client` directly; generated packages are removed; full migration complete.
