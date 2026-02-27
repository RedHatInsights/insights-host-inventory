from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from hvac import Client as VaultClient
from pydantic import BaseModel
from pydantic import SecretStr

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_DEFAULT_ENVIRONMENT = "stage"

_VAULT_PREFIX = "vault:"

ENV_VAR_CONFIG_PATH = "HBI_TEST_CONFIG_PATH"
ENV_VAR_ENVIRONMENT = "HBI_TEST_ENV"
ENV_VAR_AUTH_TYPE = "HBI_TEST_AUTH_TYPE"
ENV_VAR_VAULT_ADDR = "HBI_TEST_VAULT_ADDR"
ENV_VAR_VAULT_MOUNT_POINT = "HBI_TEST_VAULT_MOUNT_POINT"

logger = logging.getLogger(__name__)


class BasicAuth(BaseModel):
    username: str
    password: SecretStr


class User(BaseModel):
    basic_auth: BasicAuth | None = None


class Config(BaseModel):
    base_url: str
    hbi_api_base_path: str
    ingress_api_base_path: str
    default_auth_type: str = "basic_auth"
    default_user: str = "insights_inventory_qe"
    proxy: str | None = None
    users: dict[str, User]

    @property
    def hbi_api_url(self) -> str:
        return f"{self.base_url}{self.hbi_api_base_path}"

    @property
    def ingress_api_url(self) -> str:
        return f"{self.base_url}{self.ingress_api_base_path}"


def _parse_vault_ref(value: str) -> tuple[str, str]:
    """Parse a 'vault:path/to/secret#key' reference into (path, key)."""
    ref = value[len(_VAULT_PREFIX) :]
    if "#" not in ref:
        raise ValueError(f"Vault reference must include a key after '#': {value}")
    path, key = ref.rsplit("#", 1)
    return path, key


def _fetch_vault_secret(vault_client: VaultClient, mount_point: str, path: str, key: str) -> str:
    """Fetch a single secret value from Vault. Errors never expose secret data."""
    try:
        response = vault_client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=mount_point, raise_on_deleted_version=True
        )
        secret_data = response["data"]["data"]
    except Exception:
        raise ValueError(f"Failed to read Vault secret at '{path}'") from None

    if key not in secret_data:
        available = ", ".join(secret_data.keys())
        raise ValueError(f"Key '{key}' not found at Vault path '{path}'. Available keys: {available}")

    return secret_data[key]


def _resolve_vault_refs(data: Any, vault_client: VaultClient, mount_point: str) -> Any:
    """Recursively walk a dict/list and replace 'vault:...' strings with fetched secrets."""
    if isinstance(data, str) and data.startswith(_VAULT_PREFIX):
        path, key = _parse_vault_ref(data)
        logger.info(f"Fetching secret from Vault: {mount_point}/{path}#{key}")
        return _fetch_vault_secret(vault_client, mount_point, path, key)
    elif isinstance(data, dict):
        return {k: _resolve_vault_refs(v, vault_client, mount_point) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_vault_refs(item, vault_client, mount_point) for item in data]
    return data


def _create_vault_client() -> VaultClient:
    """Create and authenticate a Vault client via the vault CLI (interactive OIDC)."""
    import subprocess

    vault_addr = os.environ.get(ENV_VAR_VAULT_ADDR)

    if not vault_addr:
        raise ValueError(f"Vault address is required. Set the {ENV_VAR_VAULT_ADDR} environment variable.")

    logger.info("Authenticating to Vault via OIDC (this may open a browser)...")
    result = subprocess.run(
        ["vault", "login", "-method=oidc", "-token-only"],
        env={**os.environ, "VAULT_ADDR": vault_addr},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"Vault login failed: {result.stderr.strip()}")

    token = result.stdout.strip()
    client = VaultClient(url=vault_addr, token=token)

    if not client.is_authenticated():
        raise ValueError("Vault authentication failed.")

    logger.info("Successfully authenticated to Vault via OIDC")
    return client


def _resolve_base_url_from_oc() -> str:
    """Fetch the base URL from OpenShift via the current namespace's FrontendEnvironment."""
    from ocviapy import get_current_namespace
    from ocviapy import get_json

    namespace = get_current_namespace()
    fe_env = get_json("frontendenvironment", f"env-{namespace}")
    hostname = fe_env.get("spec", {}).get("hostname", "")

    if not hostname:
        raise ValueError(f"Could not resolve hostname from FrontendEnvironment in namespace '{namespace}'")

    base_url = f"https://{hostname}"
    logger.info(f"Resolved base_url from OpenShift: {base_url}")
    return base_url


def load_config() -> Config:
    config_path = Path(os.environ.get(ENV_VAR_CONFIG_PATH, _DEFAULT_CONFIG_PATH))
    environment = os.environ.get(ENV_VAR_ENVIRONMENT, _DEFAULT_ENVIRONMENT)

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    defaults = raw.pop("default", {})

    if environment not in raw:
        available = ", ".join(raw.keys())
        raise ValueError(f"Environment '{environment}' not found in {config_path}. Available: {available}")

    merged = {**defaults, **raw[environment]}

    if "base_url" not in merged:
        if environment == "ephemeral":
            merged["base_url"] = _resolve_base_url_from_oc()
        else:
            raise ValueError(f"'base_url' not found in {config_path} for '{environment}' environment.")

    vault_client = _create_vault_client()
    mount_point = os.environ.get(ENV_VAR_VAULT_MOUNT_POINT, "insights")
    merged = _resolve_vault_refs(merged, vault_client, mount_point)

    return Config.model_validate(merged)
