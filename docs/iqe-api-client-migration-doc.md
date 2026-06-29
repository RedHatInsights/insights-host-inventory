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
Test → Wrapper (HostsAPIWrapper.host_checkin_response) → BaseAPIWrapper → app.http_client (RobustSession)
```

The POC introduces a `BaseAPIWrapper` base class that wraps IQE's `app.http_client` (a `RobustSession` that already handles auth and config). A URL helper prepends the versioned base path. All existing V1 wrapper methods remain on the apigen path untouched.

### Before / After

**Before — no `host_checkin` wrapper method exists in `HostsAPIWrapper`:**

```python
# HostsAPIWrapper has no host_checkin method today.
# The apigen HostsApi does have api_host_host_checkin, but it is never
# exposed through HostsAPIWrapper — callers use raw_api directly or skip it.
```

**After (using `BaseAPIWrapper`):**

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

    def host_checkin_response(
        self,
        *,
        insights_id: str | None = None,
        fqdn: str | None = None,
        subscription_manager_id: str | None = None,
        checkin_frequency: int | None = None,
    ) -> dict:
        """Check in a host via POST /api/inventory/v1/hosts/checkin.

        Updates staleness timestamps for an existing host identified by
        canonical facts. At least one canonical fact must be provided.
        Returns the raw response dict. No apigen types are used.
        Only used in Create Hosts / checkin tests.
        """
        body = {
            k: v for k, v in {
                "insights_id": insights_id,
                "fqdn": fqdn,
                "subscription_manager_id": subscription_manager_id,
                "checkin_frequency": checkin_frequency,
            }.items() if v is not None
        }
        response = self._base_wrapper.post("/hosts/checkin", json=body)
        response.raise_for_status()
        return response.json()
```



### POC Scope

**In scope (this POC):**

- `BaseAPIWrapper` base class using IQE's `app.http_client` (`RobustSession`) with a versioned URL helper
- A single new method `host_checkin_response` on `HostsAPIWrapper` that calls `POST /api/inventory/v1/hosts/checkin` via `BaseAPIWrapper`
- **Apply this new method only in Create Hosts / checkin tests**
- Return plain dicts from the new method (tests assert on dict keys)

**Why "Create Hosts" tests cannot use `BaseAPIWrapper`:**

The initial POC plan was to target Create Hosts tests because adding a new host-creation wrapper would not affect other services. However, HBI does **not** expose a `POST /hosts` REST endpoint in V1 — the V1 spec only defines `GET` and `DELETE` on `/hosts`. Hosts are created exclusively via:
- **Kafka ingestion pipeline** — `kafka_interaction.py` sends host messages to the ingress topic
- **Ingress upload** — `uploads.py` uploads insights archives via `IngressApi`

Neither path goes through a REST endpoint that `BaseAPIWrapper` could wrap. There is nothing to migrate.

**Why `POST /hosts/checkin` is the right POC target instead:**

- `POST /hosts/checkin` exists in the V1 spec (operationId: `api.host.host_checkin`). It accepts canonical facts (`insights_id`, `fqdn`, `subscription_manager_id`, etc.) plus an optional `checkin_frequency` (minutes), and returns a `HostOut`.
- `HostsAPIWrapper` has **no** `host_checkin` method today — there are no existing callers to break.
- It is a host write operation in the same domain as Create Hosts, demonstrating `BaseAPIWrapper` on a V1 write path without any cross-team risk.
- Adding a new `BaseAPIWrapper`-backed method introduces zero risk to downstream services or other IQE plugins.

**Out of scope for this POC:**

- Migrating any existing V1 endpoints (GET, PATCH, DELETE /hosts, etc.) — other IQE plugins depend on the apigen model objects returned by those wrappers
- V2 endpoint wrappers (deferred; original design doc covers these — see `RHINENG-26236-epic.v1.md`)
- Removing `iqe_host_inventory_api/` and `iqe_host_inventory_api_v7/` packages



### Future: Broader V1 Migration

`BaseAPIWrapper` is version-aware — it accepts `api_version` as a parameter, so both V1 and V2 wrappers can use it. The base class is ready for broader use today.

**V2 endpoints:** Can be added as new `BaseAPIWrapper`-backed methods immediately (see original design doc `RHINENG-26236-epic.v1.md`).

**Remaining V1 endpoints:** Do not migrate without first coordinating with other IQE plugin teams. Other plugins depend on the typed apigen model objects (e.g., `HostOut`, `HostQueryOutput`) returned by the current V1 wrappers. Migrating those to return plain dicts would break them. V1 migration requires a cross-team coordination effort.

### Deliverables

1. **PR 1 (POC)** — `BaseAPIWrapper` base class + `host_checkin_response` method on `HostsAPIWrapper` using `POST /api/inventory/v1/hosts/checkin` + at least one checkin test using the new method and passing
2. **PR 2** —
  ***Identify*** other V1 endpoints which could be migrated to use the `BaseAPIWrapper` without affecting other services/plugins, and ***migrate*** them to use the `BaseAPIWrapper`.
3. **Future** — ***Create*** new tests for V2 endpoints to use `BaseAPIWrapper` and ***broader*** V1 migration (requires cross-team coordination, tracked separately)
