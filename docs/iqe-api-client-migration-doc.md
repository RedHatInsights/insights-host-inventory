## IQE API Client Migration: Apigen to Direct Requests

### Context

The `iqe-host-inventory-plugin` currently uses auto-generated OpenAPI bindings to interact with the HBI API. That approach has become increasingly costly:

1. **Regeneration overhead** — spec changes require regenerating and reviewing large amounts of generated code.
2. **Abstraction mismatch** — test failures are debugged through wrapper -> apigen client -> underlying HTTP client instead of through a thin, explicit request path.
3. **Tight coupling to spec details** — generated method names are derived from OpenAPI metadata such as `operationId`, so spec refactors can break call sites even when endpoint behavior is unchanged.
4. **V2 friction** — the V2 API introduces new endpoints and renamed operations. Carrying the generated-client pattern forward would preserve the same maintenance and debugging problems in the new surface area.

At the same time, a full replacement of the existing V1 wrappers is not safe as a local refactor. Other IQE plugins and services consume `iqe-host-inventory-plugin`, and current V1 wrappers return apigen-generated model objects such as `HostOut` and `HostQueryOutput`. Replacing those return types broadly would create downstream compatibility breaks and requires coordinated migration work across teams.

### Architecture

**Current**

```
Test -> Wrapper -> Apigen client -> ApiClient -> urllib3
```

**Target**

```
Test -> Wrapper -> BaseAPIWrapper -> app.http_client
```

The target architecture introduces a thin `BaseAPIWrapper` built on IQE's existing `app.http_client`. That gives wrapper methods a direct and explicit HTTP path without requiring generated bindings for new work.

### Decision

Introduce `BaseAPIWrapper` as the preferred foundation for new wrapper methods and for V2 wrapper development.

Existing V1 wrapper methods will remain on the apigen-backed path until downstream consumer impact is understood and coordinated. During the migration period, apigen-backed wrappers and direct-request wrappers are expected to coexist.

### Consequences

**Positive**

- New work is no longer forced through generated clients.
- Request behavior is easier to trace and debug.
- V2 wrapper development can proceed without deep coupling to apigen output.

**Negative**

- The plugin will temporarily support two wrapper patterns.
- Return types may remain inconsistent across wrappers during the transition.
- Broader V1 migration is still blocked on downstream consumer coordination.

### Status

Initial adoption should be limited to low-risk or newly introduced wrapper methods where no existing downstream compatibility contract is being changed.
