# Token Refresh

Regenerates SSO offline tokens for all HBI test users in a given org
and updates the corresponding HashiCorp Vault secret. This automates
the manual process of logging into each user, generating a token from
the API management page, and copying it to Vault.

## Prerequisites

1. **VPN** — connected (required for stage environment)
2. **User accounts** — already created via `scripts/rbac-setup/create_users.yml`
3. **Passwords set** — all users in the org must have the same password
4. **Vault access** — you need a Vault token with read/write access to the
   target secret path (see [Getting a Vault Token](#getting-a-vault-token))

## Usage

```bash
cd scripts/token-refresh

# Interactive mode — prompts for all inputs
uv run --with requests --with pyyaml refresh_tokens.py

# Or pass arguments directly
uv run --with requests --with pyyaml refresh_tokens.py \
  --env stage \
  --prefix insights_inventory_qe \
  --password '<the_shared_password>' \
  --proxy '<stage-proxy>' \
  --vault-token '<token>' \
  --vault-path '<path/to/vault/secret>'

# Dry run — generate tokens but don't update Vault
uv run --with requests --with pyyaml refresh_tokens.py --dry-run
```

It is recommended to specify the password and vault token in an interactive mode
(without passing `--password` and `--vault-token`) to keep these secrets out of
your bash history.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--env` | Yes | `stage` or `prod` |
| `--prefix` | Yes | User prefix (e.g. `insights_inventory_qe`). Usernames are `<prefix>-<suffix>` |
| `--password` | Yes | Shared password for all users in this org |
| `--proxy` | Stage only | HTTPS proxy URL |
| `--vault-token` | Yes | Vault authentication token |
| `--vault-path` | Yes | Vault secret path (e.g. `secrets/qe/stage/users/insights_inventory_qe`) |
| `--dry-run` | No | Generate tokens without updating Vault |

All arguments can be omitted — the script will prompt for them interactively.

## Getting a Vault Token

1. Open https://vault.devshift.net in your browser
2. Log in (OIDC)
3. Click your profile icon (top right)
4. Click **"Copy token"**
5. Paste when prompted by the script

The token is typically valid for a few hours. If you get a 403 error,
generate a fresh token.

## How It Works

The script generates offline tokens using the same SSO authorization code
flow that the Red Hat API management page uses:

1. Loads user suffixes from `scripts/rbac-setup/vars/users.yml`
2. For each user (`<prefix>-<suffix>`):
   - Submits credentials to the SSO login form
   - Captures the authorization code from the redirect
   - Exchanges the code for an offline token
3. Reads the current Vault secret at the given path
4. Updates only the `<suffix>-refresh_token` keys (preserves all other keys)
5. Writes back to Vault with check-and-set (CAS) to prevent overwriting
   concurrent changes

No browser or Selenium is needed — everything is done via HTTP requests.

## Vault Secret Format

The Vault secret at the configured path contains one key per user:

```
inv-admin-refresh_token: <token1>
hosts-admin-refresh_token: <token2>
hosts-viewer-refresh_token: <token3>
no-perms-refresh_token: <token4>
...
```

The suffixes match those defined in `scripts/rbac-setup/vars/users.yml`.

## Vault Path Reference

- **Vault URL:** https://vault.devshift.net
- **KV v2 mount:** `insights`
- **Example path:** `secrets/qe/stage/users/insights_inventory_qe`
- **Full API URL:** `https://vault.devshift.net/v1/insights/data/secrets/qe/stage/users/insights_inventory_qe`
- **UI URL:** `https://vault.devshift.net/ui/vault/secrets/insights/kv/secrets%2Fqe%2Fstage%2Fusers%2Finsights_inventory_qe/details`
