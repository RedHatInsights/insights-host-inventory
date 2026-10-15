"""Regenerate SSO offline tokens for HBI test users and update Vault.

Automates steps 3-4 from the "After User Creation" section of
scripts/rbac-setup/README.md: generating offline tokens via the SSO
authorization code flow and storing them in HashiCorp Vault.
"""

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

import requests
import yaml

USERS_YML = Path(__file__).resolve().parent.parent / "rbac-setup" / "vars" / "users.yml"

ENV_CONFIG = {
    "stage": {
        "sso_url": "https://sso.stage.redhat.com",
        "redirect_uri": "https://access.stage.redhat.com/management/api/token",
    },
    "prod": {
        "sso_url": "https://sso.redhat.com",
        "redirect_uri": "https://access.redhat.com/management/api/token",
    },
}

CLIENT_ID = "rhsm-api"
SCOPE = "offline_access api.graphql"

VAULT_URL = "https://vault.devshift.net"
VAULT_MOUNT = "insights"


def load_user_suffixes() -> list[str]:
    with open(USERS_YML) as f:
        data = yaml.safe_load(f)
    return [u["suffix"] for u in data["users"]]


def generate_offline_token(env: str, username: str, password: str, proxy: str | None = None) -> str:
    """Run the SSO authorization code flow and return the offline/refresh token."""
    cfg = ENV_CONFIG[env]
    realm_path = "/auth/realms/redhat-external/protocol/openid-connect"
    auth_url = f"{cfg['sso_url']}{realm_path}/auth"
    token_url = f"{cfg['sso_url']}{realm_path}/token"

    session = requests.Session()
    if proxy:
        session.proxies.update({"https": proxy, "http": proxy})

    # Step 1: GET the authorize endpoint → redirects to login form
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": SCOPE,
    }
    resp = session.get(auth_url, params=auth_params, allow_redirects=True)
    resp.raise_for_status()

    # Step 2: Parse the login form action URL
    action_match = re.search(r'action="(https://[^"]*login-actions/authenticate[^"]*)"', resp.text)
    if not action_match:
        raise RuntimeError(f"Could not find login form in SSO response (URL: {resp.url})")

    form_action = action_match.group(1).replace("&amp;", "&")

    # Step 3: POST credentials
    resp = session.post(form_action, data={"username": username, "password": password}, allow_redirects=False)

    # Step 4: Follow redirects to capture the authorization code
    for _ in range(10):
        if resp.status_code not in (301, 302, 303, 307, 308):
            break
        location = resp.headers.get("Location", "")
        parsed = urllib.parse.urlparse(location)
        query = urllib.parse.parse_qs(parsed.query)

        if "code" in query:
            code = query["code"][0]

            # Step 5: Exchange code for tokens
            token_data = {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
            }
            token_resp = session.post(token_url, data=token_data)
            token_resp.raise_for_status()
            tokens = token_resp.json()

            if "refresh_token" not in tokens:
                raise RuntimeError(f"No refresh_token in SSO response: {tokens}")

            return tokens["refresh_token"]

        resp = session.get(location, allow_redirects=False)

    if resp.status_code == 200 and "login-actions" in resp.url:
        raise RuntimeError("Login failed — check username/password")

    raise RuntimeError(f"Never received authorization code (last status: {resp.status_code}, url: {resp.url})")


def vault_read(vault_token: str, secret_path: str) -> tuple[dict[str, str], int]:
    """Read current secret data and version from Vault KV v2."""
    url = f"{VAULT_URL}/v1/{VAULT_MOUNT}/data/{secret_path}"
    headers = {"X-Vault-Token": vault_token}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    result = resp.json()
    data = result.get("data", {}).get("data", {})
    version = result.get("data", {}).get("metadata", {}).get("version")
    return data, version


def vault_write(vault_token: str, secret_path: str, data: dict[str, str], cas_version: int) -> int:
    """Write secret data to Vault KV v2 with check-and-set."""
    url = f"{VAULT_URL}/v1/{VAULT_MOUNT}/data/{secret_path}"
    headers = {"X-Vault-Token": vault_token}
    payload = {
        "data": data,
        "options": {"cas": cas_version},
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("version")


def prompt_inputs(args: argparse.Namespace) -> tuple[str, str, str, str | None, str, str]:
    """Prompt for any inputs not provided via CLI args."""
    env = args.env
    if not env:
        env = input("Environment (stage/prod): ").strip().lower()
        if env not in ENV_CONFIG:
            print(f"Invalid environment: {env}")
            sys.exit(1)

    prefix = args.prefix or input("User prefix (e.g. 'insights_inventory_qe'): ").strip()
    password = args.password or input("Password (shared by all users in this org): ").strip()

    proxy = args.proxy
    if env == "stage" and not proxy:
        proxy = input("Stage proxy (leave empty if not needed): ").strip() or None

    vault_token = args.vault_token or input("Vault token: ").strip()
    vault_path = (
        args.vault_path or input("Vault secret path (e.g. 'secrets/qe/stage/users/insights_inventory_qe'): ").strip()
    )

    return env, prefix, password, proxy, vault_token, vault_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate SSO offline tokens for HBI test users and update Vault.",
    )
    parser.add_argument("--env", choices=["stage", "prod"], help="Target environment")
    parser.add_argument("--prefix", help="User prefix (e.g. 'insights_inventory_qe')")
    parser.add_argument("--password", help="Shared password for all users in this org")
    parser.add_argument("--proxy", help="HTTPS proxy (required for stage)")
    parser.add_argument("--vault-token", help="Vault authentication token")
    parser.add_argument("--vault-path", help="Vault secret path (e.g. 'secrets/qe/stage/users/insights_inventory_qe')")
    parser.add_argument("--dry-run", action="store_true", help="Generate tokens but don't update Vault")
    args = parser.parse_args()

    env, prefix, password, proxy, vault_token, vault_path = prompt_inputs(args)

    suffixes = load_user_suffixes()
    print(f"\nLoaded {len(suffixes)} user suffixes from {USERS_YML.name}")

    # Generate tokens
    generated = {}
    failed = []

    for i, suffix in enumerate(suffixes, 1):
        username = f"{prefix}-{suffix}"
        print(f"\n[{i}/{len(suffixes)}] {username}...", end=" ", flush=True)
        try:
            token = generate_offline_token(env, username, password, proxy)
            generated[suffix] = token
            print(f"OK ({len(token)} chars)")
        except Exception as e:
            failed.append((suffix, str(e)))
            print(f"FAILED: {e}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Generated: {len(generated)}/{len(suffixes)}")
    if failed:
        print(f"Failed:    {len(failed)}/{len(suffixes)}")
        for suffix, error in failed:
            print(f"  - {suffix}: {error}")

    if not generated:
        print("\nNo tokens generated. Nothing to write to Vault.")
        sys.exit(1)

    if args.dry_run:
        print("\n--dry-run: Skipping Vault update.")
        return

    # Update Vault
    print(f"\nReading current Vault secret at: {vault_path}")
    try:
        vault_data, vault_version = vault_read(vault_token, vault_path)
        print(f"  Current version: {vault_version}, keys: {len(vault_data)}")
    except requests.RequestException as e:
        print(f"  ERROR reading Vault: {e}")
        sys.exit(1)

    # Update only the generated token keys
    updated_data = dict(vault_data)
    for suffix, token in generated.items():
        key = f"{suffix}-refresh_token"
        updated_data[key] = token

    print(f"Updating {len(generated)} token(s) in Vault...")
    try:
        new_version = vault_write(vault_token, vault_path, updated_data, vault_version)
        print(f"  Vault updated successfully. New version: {new_version}")
    except requests.RequestException as e:
        print(f"  ERROR writing to Vault: {e}")
        sys.exit(1)

    print("\nDone!")


if __name__ == "__main__":
    main()
