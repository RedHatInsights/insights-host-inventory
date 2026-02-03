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
# Quick activation
./iqe-shell.sh

# Or manually
export PIPENV_PIPFILE=Pipfile.iqe
pipenv shell
```

### IQE dependency update

Unfortunatelly the IQE dependencies mostly live in a Red Hat private repo.

To update them manually please run the following command and push the changes to the lockfile as PR.

```bash
PIPENV_PIPFILE=Pipfile.iqe pipenv lock --dev -v
```

Then run the setup script to install the updated dependencies.
```bash
# From repository root
./setup-iqe.sh
```

## Running Tests

### Run a Single Test
```bash
# Run specific test by name
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -k test_create_single_host

# Run specific test file
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory tests/rest/test_hosts.py::test_create_single_host
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
```bash
echo $PIPENV_PIPFILE
# Empty = main HBI environment
# Pipfile.iqe = IQE test environment
```

## Further Reading
- Full IQE plugin documentation: `iqe-host-inventory-plugin/README.md`
- [IQE Core Documentation](https://insights-qe.pages.redhat.com/iqe-core-docs/)
