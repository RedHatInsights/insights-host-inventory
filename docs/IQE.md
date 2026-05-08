# IQE Test Environment Setup

Quick guide to setting up and running IQE tests for the Host Based Inventory service.

## Prerequisites

### 1. VPN and Certificates
- Connect to the Red Hat VPN
- Install [Red Hat certificates](https://source.redhat.com/groups/public/identity-access-management/it_iam_pki_rhcs_and_digicert/faqs_new_corporate_root_certificate_authority):
  ```bash
  # Add to ~/.bashrc or ~/.zshrc
  export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
  ```

### 2. Vault Access
Configure Vault for IQE credentials (add to `~/.bashrc` or `~/.zshrc`):
```bash
export DYNACONF_IQE_VAULT_LOADER_ENABLED=true
export DYNACONF_IQE_VAULT_URL="https://vault.devshift.net/"
export DYNACONF_IQE_VAULT_VERIFY=true
export DYNACONF_IQE_VAULT_MOUNT_POINT="insights"
export DYNACONF_IQE_VAULT_OIDC_AUTH="1"

# If not using Firefox or Kerberos locally:
export DYNACONF_IQE_VAULT_OIDC_HEADLESS="false"
```

**Important**: Ensure you have a user file in app-interface with `insights-qe` and `insights-engineers` roles. See [IQE documentation](https://insights-qe.pages.redhat.com/iqe-core-docs/configuration.html#getting-access) for details.

## Setup

### One-Time Setup
```bash
# From repository root
./setup-iqe.sh
```

This installs all IQE dependencies and the local plugin in editable mode.

### Activate IQE Environment
```bash
# Quick activation (spawns a shell with the plugin venv)
./iqe-shell.sh

# Or manually
cd iqe-host-inventory-plugin
uv shell
```

### IQE dependency update

Unfortunately some IQE dependencies (for example `iqe-core`) are resolved from a Red Hat private index (`cqt-pypi` in `pyproject.toml`). Locking requires VPN and a trust store that includes Red Hat corporate CAs (`native-tls` is enabled for uv in the plugin project).

To refresh the lockfile after editing plugin dependencies, run from the repository root and open a PR with the updated `iqe-host-inventory-plugin/uv.lock`:

```bash
cd iqe-host-inventory-plugin
uv lock --python 3.12
```

Then run the setup script to install the updated dependencies.
```bash
# From repository root
./setup-iqe.sh
```

## Running Tests

### Run a Single Test
```bash
# Run specific test file
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -k test_outage

# Run specific test by name
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory iqe-host-inventory-plugin/iqe_host_inventory/tests/rest/test_outage.py::test_outage_get_host_list
```

### Common Test Commands
```bash
# Smoke tests only
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'backend and smoke and not ephemeral'

# All backend tests (takes ~1 hour)
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'backend and not ephemeral'
```

### Environment Options
Change `ENV_FOR_DYNACONF` to test different environments:
- `stage_proxy` - Stage environment (default)
- `prod` - Production


[See more in Full IQE docs](#further_reading) section below including also `fedramp_stage_proxy`.

## Custom IQE Users

By default, IQE tests use shared test users defined in `iqe_host_inventory/conf/host_inventory.default.yaml`. For isolated testing with your own org_id and feature flag configuration, you can create custom users.

### Using Custom Users

**1. Create a local configuration file:**
```bash
# This file is gitignored and contains your credentials
iqe-host-inventory-plugin/iqe_host_inventory/conf/host_inventory.local.yaml
```

**2. Basic structure:**
```yaml
stage: &stage
  legacy_hostname: "YOUR_STAGE_API_HOST"
  turnpike_base_url: "YOUR_RBAC_URL"
  default_user: your_custom_user
  users:
    your_custom_user:
      auth:
        username: "your-username"
        password: "your-password"
        refresh_token: "YOUR_REFRESH_TOKEN"
      identity:
        account_number: "YOUR_ACCOUNT_NUMBER"
        org_id: "YOUR_ORG_ID"

stage_proxy: *stage
```

**3. Run tests with your custom user:**
```bash
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory --user your_custom_user -m smoke
```

### Full Setup Guide

For complete instructions on creating custom users (including user creation, token generation, and configuration):

📘 **[Internal Documentation: Creating Custom IQE Users](https://redhat.atlassian.net/wiki/spaces/~70121821d7ad2679b4fd7ab4a5dabf625c5a0/pages/384305391/Creating+Custom+IQE+Users+for+Stage+Cluster)**

**Benefits of custom users:**
- Isolated org_id for testing (no conflicts with other teams)
- Control your own feature flags
- Test with specific RBAC configurations
- Debug without affecting shared test data

## Troubleshooting

**Certificate errors during install:**
```bash
# Linux
sudo curl https://certs.corp.redhat.com/certs/Current-IT-Root-CAs.pem -o /etc/pki/ca-trust/source/anchors/Current-IT-Root-CAs.pem
sudo update-ca-trust

# macOS
cat `python -m certifi` > ~/bundle.crt
curl https://certs.corp.redhat.com/certs/Current-IT-Root-CAs.pem >> ~/bundle.crt
export REQUESTS_CA_BUNDLE=~/bundle.crt
```

**Plugin not found:**
Check installation:
```bash
iqe plugin list
```

**Which environment am I in?**
- Main HBI app: virtualenv at the repository root (`.venv` after `uv sync` there).
- IQE: virtualenv under `iqe-host-inventory-plugin/.venv` after `./setup-iqe.sh` or `uv sync` in that directory.

## Further Reading
- Full IQE plugin documentation: `iqe-host-inventory-plugin/README.md`
- [IQE Core Documentation](https://insights-qe.pages.redhat.com/iqe-core-docs/)
