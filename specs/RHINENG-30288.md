# Spec: RHINENG-30288

## Summary
Add deprecation notice banners to the HBI (Host Based Inventory) service UI, notifying users of the service's EOL date, migration path, and a link to the official announcement.

## Root Cause
The HBI service (a Flask/Connexion REST API) currently has no deprecation/decommission notices visible to API consumers. The 'UI' for this backend service consists of: (1) the Connexion-served Swagger/OpenAPI UI at the API endpoints, and (2) HTTP response headers on all API calls. There is no existing mechanism to inject deprecation headers (RFC 8594 `Deprecation`/`Sunset` headers) or to surface EOL notices in the OpenAPI spec's info section. The `app/__init__.py` already has an `after_request` hook pattern (`after_request_org_check`) that can be extended, and `app/config.py` already reads numerous env vars — both are the natural integration points. The OpenAPI spec (`swagger/api.spec.yaml` / `swagger/openapi.json`) `info.description` field is another place to embed the notice for Swagger UI visibility.

## Plan

- `app/config.py` (modify): Add three new env-var-backed attributes to the `Config` class shared init block (near the `consoledot_hostname` / `base_ui_url` pattern): a boolean `deprecation_banner_enabled` (env `INVENTORY_DEPRECATION_BANNER_ENABLED`, default `False`), a string `deprecation_sunset_date` (env `INVENTORY_DEPRECATION_SUNSET_DATE`, default empty string), and a string `deprecation_announcement_url` (env `INVENTORY_DEPRECATION_ANNOUNCEMENT_URL`, default empty string).

- `app/__init__.py` (modify): Inside `create_app`, register a new `@flask_app.after_request` function named `add_deprecation_headers` immediately after `after_request_org_check`. When `app_config.deprecation_banner_enabled` is `True`, the function should inject three headers into every response: `Deprecation` (using the sunset date per RFC 8594), `Sunset` (HTTP-date formatted), and `Link` (pointing to the announcement URL with `rel="deprecation"`). The config object is already stored at `flask_app.config['INVENTORY_CONFIG']`.

- `swagger/api.spec.yaml` (modify): Prepend a bold deprecation notice to the `info.description` field that includes the service EOL date, a pointer to the migration path, and the announcement URL. This surfaces the notice prominently in the Swagger UI for anyone browsing the API documentation.

- `swagger/openapi.json` (modify): Update the `info.description` field to match the deprecation notice added to `api.spec.yaml`. Since no build script auto-generates this JSON from the YAML, both files must be kept in sync manually; this file is what Connexion's `TranslatingParser` actually loads at runtime.

- `tests/test_unit.py` (modify): Add unit tests covering: (1) that `Config` correctly reads `INVENTORY_DEPRECATION_BANNER_ENABLED`, `INVENTORY_DEPRECATION_SUNSET_DATE`, and `INVENTORY_DEPRECATION_ANNOUNCEMENT_URL` from environment variables with correct defaults; (2) that a Flask test client request returns `Deprecation`, `Sunset`, and `Link` headers when the feature flag is enabled; and (3) that those headers are absent when the flag is disabled. Model config tests after `test_config_default_settings` / `test_configuration_with_env_vars` using `set_environment`, and header tests using `create_app(RuntimeEnvironment.TEST)` with a test client.

## Constraints
- swagger/openapi.json must be kept in sync with swagger/api.spec.yaml — there is no auto-generation pipeline detected; both must be edited in the same PR.
- The feature must be off by default (env var absent or set to 'false') to avoid impacting existing environments that have not yet set the new env vars.
