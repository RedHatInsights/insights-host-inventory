# RBAC Setup for HBI Tests

Ansible playbooks that provision dedicated Red Hat users with specific RBAC
permissions for HBI testing. Each user gets exactly one role (or zero
for the no-permissions user), eliminating the need to reconfigure RBAC
between test classes.

## Prerequisites

1. **Ansible** — `pip install ansible` or your system's package manager
2. **VPN** — connected (required for stage environment)
3. **Offline token** — generate from the API tokens page:
   - Prod: https://access.redhat.com/management/api
   - Stage: https://access.stage.redhat.com/management/api
4. **User accounts** — created via `create_users.yml` (uses Red Hat Account API)

## Quick Start

```bash
cd scripts/rbac-setup

# 1. Create any missing users (auto-discovers username, email, and account ID)
ansible-playbook create_users.yml \
  -e "offline_token=YOUR_TOKEN" \
  -e "target_env=prod"

# 2. Configure RBAC permissions (choose v1 OR v2 — never both on same org)
ansible-playbook setup_rbac_v1.yml \
  -e "offline_token=YOUR_TOKEN" \
  -e "target_env=prod"

# Or for v2:
ansible-playbook setup_rbac_v2.yml \
  -e "offline_token=YOUR_TOKEN" \
  -e "target_env=prod"

# 3. To clean up (remove test groups and custom roles)
ansible-playbook teardown_rbac.yml \
  -e "offline_token=YOUR_TOKEN" \
  -e "target_env=prod" \
  -e "rbac_version=v1"
```

### Stage Environment

Stage requires VPN access and an HTTP proxy:

```bash
ansible-playbook setup_rbac_v1.yml \
  -e "offline_token=YOUR_TOKEN" \
  -e "target_env=stage" \
  -e "stage_proxy=http://YOUR_PROXY_HOST:PORT"
```

## CRITICAL: V1 vs V2 Isolation

**Never run `setup_rbac_v2.yml` on an org that needs v1 testing.**
Making any RBAC v2 API call permanently disables v1 for that org.
The playbooks are separate files to ensure a playbook doesn't trigger
v2 APIs unintentionally, but you must make sure to always run the
correct playbook for your org.

As of June 2026, the only account where v2 should be used is
**insights-inventory-qe** on stage.

## Playbooks

| Playbook | Purpose |
|---|---|
| `create_users.yml` | Create missing users via Red Hat Account API |
| `setup_rbac_v1.yml` | Configure RBAC using v1 API only |
| `setup_rbac_v2.yml` | Configure RBAC using v2 API (with workspaces) |
| `teardown_rbac.yml` | Remove all test groups and custom roles |

## Users Created

See `vars/users.yml` for the full list. Username format:
`<org_admin_username>-<suffix>`.

### What the Setup Playbooks Do

1. **Strip the "Default access" group** — removes all roles so test users
   don't inherit unwanted permissions
2. **Clean up each user** — removes from any non-designated groups
3. **Assign the correct role** — via a dedicated `test-<suffix>` group
4. **Result** — each user has exactly the specified permissions, no more

All playbooks are idempotent and safe to re-run.

### How User Creation Works

All playbooks auto-discover the org admin's username and email from
the SSO token via `GET /account/v1/user`. `create_users.yml` additionally
discovers:

1. **Account ID** — fetched via `GET /account/v1/accounts`
2. **Existing users** — listed via `GET /account/v1/accounts/{id}/users`
3. **Missing users** — created via `POST /account/v1/accounts/{id}/users`

Each test user's email is derived from the org admin's email using `+` aliasing:
- Prod: `admin+myaccount-hosts-viewer@example.com`
- Stage: `admin+myaccount-hosts-viewer+stage@example.com`

This means all test user emails route to the org admin's inbox.

### After User Creation

The Account API creates the user accounts, but each user still needs manual
setup before it can be used in automated tests:

1. **Confirm email address** — each new user receives a confirmation email.
   Open it (most of our test users use Google Groups) and click the confirmation link.
2. **Set password** — go to the Red Hat SSO login page, click
   "Forgot your password?", and follow the email link to set a password.
   For simplicity, set the same password as the main org admin.
3. **Generate offline token** — log in as the new user and generate an
   offline token from the API tokens page:
   - Prod: https://access.redhat.com/management/api
   - Stage: https://access.stage.redhat.com/management/api
4. **Store credentials in Vault** — save the offline token for each user
   so automated tests can retrieve them at runtime. Open the vault entry
   for the org admin and add <username>-refresh_token fields.

Repeat for each user. Since all confirmation and password-reset
emails are `+` aliases, they all arrive in the org admin's inbox (or the
corresponding Google Group).

## Required Variables

| Variable | Required | Description |
|---|---|---|
| `offline_token` | Always | SSO offline token for authentication |
| `target_env` | Always | `prod` or `stage` |
| `stage_proxy` | Stage only | HTTP proxy URL (e.g., `http://squid:3128`) |
| `rbac_version` | Teardown only | `v1` or `v2` |
