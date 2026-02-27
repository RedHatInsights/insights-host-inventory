# Integration Tests

Integration tests for the Host Based Inventory (HBI) service.
These tests run against live environments (stage, prod, ephemeral)
and verify end-to-end behavior of HBI.

## Prerequisites

- Python dependencies installed via `pipenv install --dev`
- [HashiCorp Vault CLI](https://developer.hashicorp.com/vault/install)
  installed on your system

## Vault Authentication

Test credentials are stored in HashiCorp Vault. The test framework
authenticates to Vault using **interactive OIDC login** via the
`vault` CLI. This means that **every time you run the tests, a
browser window will open** prompting you to log in to Vault.
After successful authentication, the tests will proceed
automatically.

Make sure you have Vault CLI installed on your system.
Also, make sure you have set the `HBI_TEST_VAULT_ADDR` environment variable
with the correct Vault URL. You can export this variable in your `~/.bashrc`
to not forget to set it every time.

## Running the Tests

The integration tests are excluded from the default `pytest` run,
to prevent conflicts with the unit tests.
To run them, target the `integration_tests/tests` directory
explicitly:

```bash
pytest integration_tests/tests
```

### Selecting an Environment

By default, the tests run against **stage**. Set `HBI_TEST_ENV`
to change the target environment:

```bash
# Run against prod
HBI_TEST_ENV=prod pytest integration_tests/tests

# Run against an ephemeral environment (requires deployed namespace)
HBI_TEST_ENV=ephemeral pytest integration_tests/tests
```

For ephemeral environments, the API base URL is resolved
automatically from OpenShift via `oc`, so you must be logged in
to the correct cluster and select correct namespace via `oc project <namespace>`
before running the tests.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `HBI_TEST_VAULT_ADDR` | Yes | - | Vault server URL |
| `HBI_TEST_ENV` | No | `stage` | Target environment |
| `HBI_TEST_VAULT_MOUNT_POINT` | No | `insights` | Vault mount point |
| `HBI_TEST_AUTH_TYPE` | No | `basic_auth` | Auth type to use |
| `HBI_TEST_CONFIG_PATH` | No | `config.yaml` | Path to config file |

## Configuration

Environment-specific settings are defined in `config.yaml`.
Each environment section can include:

- `base_url` - API base URL (optional for ephemeral, where it's resolved via `oc`)
- `proxy` - HTTP proxy URL (required in Stage)
- `default_user` - Default user for authentication
- `users` - User credentials (can reference Vault secrets
  with `vault:path/to/secret#key`)

A `default` section provides shared values inherited by all
environments.

## Project Structure

```
integration_tests/
  config.py          # Config loading, Vault integration
  config.yaml        # Per-environment settings
  data/archives/     # Sample archives for host creation
  tests/
    conftest.py      # Pytest fixtures
    test_*.py        # Test files
  utils/
    app.py           # TestApp aggregate
    archive.py       # Archive preparation and upload
    rest_api.py      # HBI REST API client
```
