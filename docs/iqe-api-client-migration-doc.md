## Epic: IQE API Client Migration — Apigen to Direct Requests

### Problem

The IQE test suite depends on auto-generated OpenAPI bindings (`iqe apigen` / `openapi-generator-cli 7.6.0`) to interact with the HBI API. This creates several problems:

1. **Regeneration overhead** — every spec change requires running `iqe apigen generate-api`, which produces ~3.7MB of generated code across two packages (`iqe_host_inventory_api/` at 1.9MB, `iqe_host_inventory_api_v7/` at 1.8MB)
2. **Abstraction mismatch** — tests interact through 3 layers: wrapper → apigen API class → urllib3. Debugging HTTP failures means tracing through generated code nobody wrote or understands
3. **Tight coupling to spec format** — generated method names like `api_group_get_group_list` are derived from operationIds. Renaming an operationId (which we just did for [V2 workspaces](https://github.com/RedHatInsights/insights-host-inventory/blob/v2-api/swagger/api_v2.spec.yaml)) breaks all call sites
4. **V2 blocker** — the V2 API spec introduces new endpoints and renames. Regenerating bindings for V2 perpetuates all the above problems. Better to migrate now



### Why Full V1 Migration Is Blocked

The `iqe-host-inventory-plugin` is consumed by a number of other services and IQE plugins. Every V1 wrapper method currently returns apigen-generated model objects (e.g., `HostOut`, `HostQueryOutput`). If V1 wrappers are migrated to return plain dicts, every downstream consumer breaks. Migrating V1 wrappers requires a coordinated, cross-team effort.

### Architecture (Current → Target)

**Current:**

```
Test → Wrapper (HostsAPIWrapper) → Apigen (HostsApi) → ApiClient → urllib3
                                    ↑ ~3.7MB generated code
```

**Target (POC):**

```
Test → Wrapper (HostsAPIWrapper.create_hosts_response) → BaseAPIWrapper → app.http_client (RobustSession)
```

The POC introduces a `BaseAPIWrapper` base class that wraps IQE's `app.http_client` (a `RobustSession` that already handles auth and config). A URL helper prepends the versioned base path. All existing V1 wrapper methods remain on the apigen path untouched.

### Before / After

**Before — no** `POST /hosts` **wrapper exists** (host creation is Kafka- or ingress-based in current tests):

```python
# No REST-based create_hosts_response method exists in HostsAPIWrapper today.
# Host creation goes through Kafka (kafka_interaction.py) or ingress upload (uploads.py).
```

**After (using** `BaseAPIWrapper`**):**

```python
# base_api_wrapper.py — URL helper builds full path from versioned base
class BaseAPIWrapper:
    def __init__(self, app, api_version="v1"):
        self._app = app
        self._base_path = f"/api/inventory/{api_version}"

    @property
    def client(self):
        return self._app.http_client

    def get(self, path, **kwargs):
        return self.client.get(f"{self._base_path}{path}", **kwargs)

    def post(self, path, **kwargs):
        return self.client.post(f"{self._base_path}{path}", **kwargs)


# hosts_api.py — new method added alongside existing apigen-backed methods
class HostsAPIWrapper(BaseEntity):
    # ... all existing methods stay on apigen path, unchanged ...

    def create_hosts_response(self, host_list: list[dict]) -> dict:
        """Create hosts via POST /api/inventory/v1/hosts using direct HTTP client.

        Returns the raw response dict. No apigen types are used.
        Only used in Create Hosts tests.
        """
        response = self._base_wrapper.post("/hosts", json=host_list)
        response.raise_for_status()
        return response.json()
```



### POC Scope

**In scope (this POC):**

- `BaseAPIWrapper` base class using IQE's `app.http_client` (`RobustSession`) with a versioned URL helper
- A single new method `create_hosts_response` on `HostsAPIWrapper` that calls `POST /api/inventory/v1/hosts` via `BaseAPIWrapper`
- **Apply this new method only in Create Hosts tests** (the tests that currently create hosts via REST, or new tests that exercise `POST /hosts` directly)
- Return plain dicts from the new method (tests assert on dict keys)

**Why Create Hosts is safe to migrate first:**

- The current apigen `HostsApi` has **no** `POST /hosts` method — host creation in existing tests goes through Kafka or ingress upload. There are no callers of a `create_hosts_response` method anywhere yet.
- Adding a new method using `BaseAPIWrapper` introduces zero risk of breaking existing consumers.
- No other IQE plugin or downstream service depends on this new path.

**Out of scope for this POC:**

- Migrating any existing V1 endpoints (GET, PATCH, DELETE /hosts, etc.) — other IQE plugins depend on the apigen model objects returned by those wrappers
- V2 endpoint wrappers (deferred; original design doc covers these — see `RHINENG-26236-epic.v1.md`)
- Removing `iqe_host_inventory_api/` and `iqe_host_inventory_api_v7/` packages



### Future: Broader V1 Migration

`BaseAPIWrapper` is version-aware — it accepts `api_version` as a parameter, so both V1 and V2 wrappers can use it. The base class is ready for broader use today.

**V2 endpoints:** Can be added as new `BaseAPIWrapper`-backed methods immediately (see original design doc `RHINENG-26236-epic.v1.md`).

**Remaining V1 endpoints:** Do not migrate without first coordinating with other IQE plugin teams. Other plugins depend on the typed apigen model objects (e.g., `HostOut`, `HostQueryOutput`) returned by the current V1 wrappers. Migrating those to return plain dicts would break them. V1 migration requires a cross-team coordination effort.

### Deliverables

1. **PR 1 (POC)** — `BaseAPIWrapper` base class + `create_hosts_response` method on `HostsAPIWrapper` using `POST /api/inventory/v1/hosts` + at least one Create Hosts test using the new method and passing
2. **PR 2** —
  ***Identify*** other V1, which could be migrated to use the `BaseAPIWrapper` without affecting other services/plugins, and ****migrate*** them to use the `BaseAPIWrapper`.
3. **Future** — ***Create*** new tests for V2 endpoints to use `BaseAPIWrapper` and ***broader*** V1 migration (requires cross-team coordination, tracked separately)
