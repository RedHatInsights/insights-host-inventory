# Integration Tests

Tests for Host Based Inventory (HBI) against live stage, prod, or ephemeral environments.
They are excluded from the default `pytest` run.

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- Network access and credentials for the target environment and Vault.
- Kerberos/GSSAPI build dependencies: `gcc`, `krb5-devel`, and `krb5-workstation`
  on Fedora; `build-essential`, `libkrb5-dev`, and `krb5-user` on Debian/Ubuntu.
- A valid Kerberos ticket (`kinit`) for the default Vault login.
- For ephemeral environments, `oc` installed and logged in to the correct cluster.

## Installation and Development

Run commands from the repository root. Install the dependencies, including
`iqe-library` and its required extras:

```bash
uv sync
```

Add tests under `integration_tests/tests/`. Use the `test_app` fixture to access
the Inventory API client, archive uploader, and shared configuration:

```python
from integration_tests.utils.app import TestApp


def test_list_hosts(test_app: TestApp) -> None:
    response = test_app.hbi_api.get_host_list_response()
    assert response.status_code == 200
```

The fixture manages its HTTP session and closes it at teardown. For a different
user or authentication mode, use the `create_test_app(config, user=..., auth_type=...)`
context manager with credentials defined in the configuration.

Run static checks without contacting live services:

```bash
uv run ruff check integration_tests
uv run ruff format --check integration_tests
uv run mypy integration_tests
```

## Running Tests

```bash
# Run the full suite (stage by default)
uv run pytest integration_tests/tests

# Run only the read-only API smoke test
uv run pytest integration_tests/tests/test_smoke.py::test_hosts_status_code
```

The full suite includes tests that create hosts. Use the read-only smoke test
when you only want to verify connectivity and authentication.

### Selecting an Environment

Set `ENV_FOR_DYNACONF` to select `stage`, `prod`, or `ephemeral`:

```bash
# Prod currently has Basic credentials configured, but no JWT credentials
ENV_FOR_DYNACONF=prod DYNACONF_HTTP__DEFAULT_AUTH_TYPE=basic \
  uv run pytest integration_tests/tests/test_smoke.py::test_hosts_status_code

# Target a deployed ephemeral namespace
ENV_FOR_DYNACONF=ephemeral NAMESPACE=ephemeral-example \
  uv run pytest integration_tests/tests
```

Stage uses JWT by default; its read-only smoke test also checks certificate auth.
Ephemeral environments discover service URLs through OpenShift, provision the
configured users before tests, and use password-grant JWT authentication.
If `NAMESPACE` is omitted, the current `oc project` is used. Tests do not change
the selected project or provision users on stage/prod.

## Configuration and Vault

`integration_tests/config.yaml` defines Inventory-specific settings and users,
on top of shared `iqe-library` defaults. For local overrides, create
`integration_tests/config.local.yaml` and **do not commit it**:

```yaml
stage:
  http:
    timeout: 60
```

Local settings override the checked-in configuration; `DYNACONF_*` environment
variables take precedence over both. Use `__` for nested settings, for example
`DYNACONF_HTTP__TIMEOUT=60`.

Credentials marked with `!from_vault` are fetched lazily when accessed, not during
configuration loading or test collection. The default Vault login uses headless
Kerberos/OIDC with your existing ticket; no browser or Vault CLI is needed.
CI can supply `DYNACONF_VAULT__TOKEN`, or AppRole credentials through
`DYNACONF_VAULT__ROLE_ID` and `DYNACONF_VAULT__SECRET_ID`. A token takes precedence
over AppRole.
