# /hbi-iqe-setup - IQE Test Environment Setup

Set up the IQE (Insights Quality Engineering) local test environment for running integration tests against stage and production HBI instances.

## Instructions

### Phase 1: Check Prerequisites

Run these checks and report results before proceeding:

1. **Python version** — IQE requires Python 3.12:
   ```
   python3 --version
   ```
   If the version is not 3.12.x, stop and tell the user to install Python 3.12.

2. **pipenv** — required for managing the IQE virtualenv:
   ```
   pipenv --version
   ```
   If missing, suggest: `pip install --user pipenv`

3. **Red Hat VPN** — IQE dependencies live on internal Red Hat infrastructure (`nexus.corp.redhat.com`). Check basic connectivity:
   ```
   curl -sf --max-time 5 https://nexus.corp.redhat.com >/dev/null 2>&1 && echo "VPN: connected" || echo "VPN: NOT connected"
   ```
   If not connected, stop and tell the user: "Connect to the Red Hat VPN before running IQE setup. The IQE dependencies are hosted on internal Red Hat infrastructure and cannot be downloaded without VPN access."

4. **Red Hat CA certificates** — required for TLS connections to internal services. Check platform:
   ```
   uname -s
   ```

   - **Linux**: check if `REQUESTS_CA_BUNDLE` is set:
     ```
     echo "${REQUESTS_CA_BUNDLE:-NOT SET}"
     ```
     If not set, install the Red Hat CA certs and configure the bundle:
     ```
     sudo curl https://certs.corp.redhat.com/certs/Current-IT-Root-CAs.pem -o /etc/pki/ca-trust/source/anchors/Current-IT-Root-CAs.pem
     sudo update-ca-trust
     export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
     ```
     Then remind the user to add `export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt` to their shell profile so it persists.

   - **macOS**: check if `REQUESTS_CA_BUNDLE` is set:
     ```
     echo "${REQUESTS_CA_BUNDLE:-NOT SET}"
     ```
     If not set, build the certificate bundle and export the variable:
     ```
     cat $(python3 -m certifi) > ~/bundle.crt
     curl https://certs.corp.redhat.com/certs/Current-IT-Root-CAs.pem >> ~/bundle.crt
     export REQUESTS_CA_BUNDLE=~/bundle.crt
     ```
     Then remind the user to add `export REQUESTS_CA_BUNDLE=~/bundle.crt` to their shell profile so it persists.

5. **Pipfile.iqe** — verify the IQE Pipfile exists in the repo root:
   ```
   test -f Pipfile.iqe && echo "Pipfile.iqe: found" || echo "Pipfile.iqe: MISSING"
   ```

6. **IQE plugin directory** — verify the plugin submodule/directory exists:
   ```
   test -d iqe-host-inventory-plugin && echo "IQE plugin dir: found" || echo "IQE plugin dir: MISSING"
   ```
   If missing, suggest: `git submodule update --init --recursive`

Present a summary table of prerequisite results:

| Check | Status | Details |
|-------|--------|---------|
| Python 3.12 | OK/FAIL | version found |
| pipenv | OK/FAIL | version found |
| Red Hat VPN | OK/FAIL | connectivity |
| RH CA certs | OK/WARN | installed or remediation needed |
| Pipfile.iqe | OK/FAIL | found or missing |
| IQE plugin dir | OK/FAIL | found or missing |

If any FAIL results, stop and provide remediation steps. Do not proceed to Phase 2 until all prerequisites pass.

### Phase 2: Configure Vault Environment

Check if the Vault environment variables are already set:

```
echo "DYNACONF_IQE_VAULT_LOADER_ENABLED=${DYNACONF_IQE_VAULT_LOADER_ENABLED:-NOT SET}"
echo "DYNACONF_IQE_VAULT_URL=${DYNACONF_IQE_VAULT_URL:-NOT SET}"
echo "DYNACONF_IQE_VAULT_VERIFY=${DYNACONF_IQE_VAULT_VERIFY:-NOT SET}"
echo "DYNACONF_IQE_VAULT_MOUNT_POINT=${DYNACONF_IQE_VAULT_MOUNT_POINT:-NOT SET}"
echo "DYNACONF_IQE_VAULT_OIDC_AUTH=${DYNACONF_IQE_VAULT_OIDC_AUTH:-NOT SET}"
```

If any are not set, export them in the current session so the rest of the setup can proceed:

```
export DYNACONF_IQE_VAULT_LOADER_ENABLED=true
export DYNACONF_IQE_VAULT_URL="https://vault.devshift.net/"
export DYNACONF_IQE_VAULT_VERIFY=true
export DYNACONF_IQE_VAULT_MOUNT_POINT="insights"
export DYNACONF_IQE_VAULT_OIDC_AUTH="1"
export DYNACONF_IQE_VAULT_OIDC_HEADLESS="false"
```

Then remind the user to add these lines to their `~/.bashrc` or `~/.zshrc` so they persist across sessions:

```bash
export DYNACONF_IQE_VAULT_LOADER_ENABLED=true
export DYNACONF_IQE_VAULT_URL="https://vault.devshift.net/"
export DYNACONF_IQE_VAULT_VERIFY=true
export DYNACONF_IQE_VAULT_MOUNT_POINT="insights"
export DYNACONF_IQE_VAULT_OIDC_AUTH="1"

# If not using Firefox or Kerberos locally:
export DYNACONF_IQE_VAULT_OIDC_HEADLESS="false"
```

Also remind the user: "You need a user file in app-interface with `insights-qe` and `insights-engineers` roles. See the [IQE access documentation](https://insights-qe.pages.redhat.com/iqe-core-docs/configuration.html#getting-access) for details."

If the variables are already set, report them as configured and move on.

### Phase 3: Install IQE Dependencies

Run the setup script:

```
./setup-iqe.sh
```

This script:
- Sets `PIPENV_PIPFILE=Pipfile.iqe`
- Runs `pipenv install --dev -v` to create the IQE virtualenv and install dependencies
- Installs the local IQE plugin in editable mode via `pipenv run pip install --editable ./iqe-host-inventory-plugin`

If the script fails, check the output for common issues:
- **Certificate errors during pip install**: the Red Hat CA certs are not properly configured (see Phase 1 remediation)
- **Package resolution failures**: the VPN may have disconnected, or `nexus.corp.redhat.com` is unreachable
- **Python version mismatch**: Pipfile.iqe requires Python 3.12

### Phase 4: Verify Installation

1. Check the IQE plugin is installed and recognized:
   ```
   PIPENV_PIPFILE=Pipfile.iqe pipenv run iqe plugin list
   ```
   Verify `host_inventory` appears in the plugin list.

2. Check the virtualenv was created:
   ```
   PIPENV_PIPFILE=Pipfile.iqe pipenv --venv
   ```

3. Verify the editable plugin install:
   ```
   PIPENV_PIPFILE=Pipfile.iqe pipenv run pip show iqe-host-inventory-plugin
   ```
   Confirm the `Location` points to the local `iqe-host-inventory-plugin/` directory.

Present verification results:

| Check | Status | Details |
|-------|--------|---------|
| IQE virtualenv | OK/FAIL | path |
| host_inventory plugin | OK/FAIL | listed or not found |
| Editable install | OK/FAIL | location path |

### Phase 5: Post-Setup Summary

Report the final status and provide the quick-start reference:

**Activating the IQE environment:**

Do NOT use `pipenv shell` — it spawns a subshell that prevents switching between environments. Instead, use `source activate` directly which modifies the current shell and supports clean switching via `deactivate`:

```bash
# Activate IQE environment
export PIPENV_PIPFILE=Pipfile.iqe
source "$(pipenv --venv)/bin/activate"
```

**Running tests (from inside the IQE environment):**
```bash
# Single test
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -k test_create_single_host

# Smoke tests
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'backend and smoke and not ephemeral'

# All backend tests
ENV_FOR_DYNACONF=stage_proxy iqe tests plugin host_inventory -m 'backend and not ephemeral'
```

**Environment options for `ENV_FOR_DYNACONF`:**
- `stage_proxy` — Stage environment (default for most testing)
- `prod` — Production environment

**Switching between environments:**

There are two completely separate pipenv virtualenvs managed by two different Pipfiles:
- `Pipfile` — main HBI backend development
- `Pipfile.iqe` — IQE test environment

Use `source activate` / `deactivate` instead of `pipenv shell` so you can switch freely without exiting and re-entering shells:

```bash
# Switch to IQE environment (deactivates current venv first)
deactivate 2>/dev/null
export PIPENV_PIPFILE=Pipfile.iqe
source "$(pipenv --venv)/bin/activate"

# Switch back to main HBI environment
deactivate 2>/dev/null
unset PIPENV_PIPFILE
source "$(pipenv --venv)/bin/activate"
```

Alternatively, use `pipenv run` to execute one-off commands without activating any environment:

```bash
# Run a command in the IQE environment
PIPENV_PIPFILE=Pipfile.iqe pipenv run iqe tests plugin host_inventory -k test_create_single_host

# Run a command in the main HBI environment
pipenv run pytest --cov=.
```

**Updating IQE dependencies later:**
```bash
PIPENV_PIPFILE=Pipfile.iqe pipenv lock --dev -v
./setup-iqe.sh
```

**Tip:** Add these functions to your shell profile for convenience. Set `HBI_REPO_DIR` to your local checkout path, or let it default to the current directory:
```bash
# Set this to your insights-host-inventory checkout path
export HBI_REPO_DIR="${HBI_REPO_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"

function iqe-shell() {
    cd "${HBI_REPO_DIR:-.}" || return
    deactivate 2>/dev/null
    unset VIRTUAL_ENV
    export PIPENV_PIPFILE=Pipfile.iqe
    source "$(pipenv --venv)/bin/activate"
}

function hbi-shell() {
    cd "${HBI_REPO_DIR:-.}" || return
    deactivate 2>/dev/null
    unset VIRTUAL_ENV
    unset PIPENV_PIPFILE
    source "$(pipenv --venv)/bin/activate"
}
```

## Important Notes

- The two environments (HBI backend and IQE) are completely separate. They have different Pipfiles, different lockfiles, and different virtualenvs.
- Do NOT use `pipenv shell` — it spawns a subshell that blocks switching. Use `source "$(pipenv --venv)/bin/activate"` instead, which modifies the current shell and supports `deactivate` for clean switching.
- To check which environment you are in: `echo ${VIRTUAL_ENV}` shows the active virtualenv path. The HBI and IQE virtualenvs have different hash suffixes.
- The IQE dependencies require Red Hat VPN access — they are hosted on `nexus.corp.redhat.com`.
- For full IQE plugin documentation, see `iqe-host-inventory-plugin/README.md`.
- For IQE core documentation, see https://insights-qe.pages.redhat.com/iqe-core-docs/
