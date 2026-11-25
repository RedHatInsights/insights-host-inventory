"""GitHub App authentication for the system profile validator.

Mints a short-lived installation token for the bugkiller-agent GitHub App.
Pull-request comments are authored as ``<app-slug>[bot]``.
"""

import time
from base64 import b64decode
from datetime import datetime
from os import getenv

import jwt
from requests import Response
from requests import get
from requests import post

from app.logging import get_logger

logger = get_logger("github_app")

_API_BASE = "https://api.github.com"
_HTTP_TIMEOUT_SECONDS = 30
_TOKEN_LIFETIME_SECONDS = 600
_TOKEN_REFRESH_MARGIN_SECONDS = 300


def normalize_private_key(key: str) -> str:
    """Return a PEM private key from a raw, escaped, quoted, or base64 value."""
    if not key or not key.strip():
        raise ValueError("GitHub App private key is empty")

    stripped = key.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        stripped = stripped[1:-1].strip()

    if "\\n" in stripped:
        stripped = stripped.replace("\\n", "\n")

    if "-----BEGIN" not in stripped:
        try:
            decoded = b64decode(stripped, validate=True).decode("utf-8")
        except ValueError:
            decoded = ""
        if "-----BEGIN" not in decoded:
            raise ValueError("GitHub App private key must be a PEM key (raw or base64-encoded)")
        stripped = decoded.replace("\\n", "\n")

    return stripped.replace("\r\n", "\n").strip() + "\n"


def build_app_jwt(app_id: str, private_key: str) -> str:
    """Sign a GitHub App JWT valid for 10 minutes."""
    now = int(time.time())
    try:
        token = jwt.encode(
            {"iat": now - 60, "exp": now + _TOKEN_LIFETIME_SECONDS, "iss": str(app_id)},
            normalize_private_key(private_key),
            algorithm="RS256",
        )
    except Exception as exc:
        raise RuntimeError("Failed to sign the GitHub App JWT") from exc
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token


def _api_headers(bearer: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _credentials() -> tuple[str, str]:
    app_id = getenv("GITHUB_APP_ID", "").strip()
    private_key = getenv("GITHUB_APP_PRIVATE_KEY", "")
    if not app_id or app_id == "0" or not private_key.strip():
        raise RuntimeError(
            "GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set to the bugkiller-agent GitHub App credentials"
        )
    return app_id, private_key


def _raise_for_status(response: Response, action: str) -> None:
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub App {action} failed with status {response.status_code}: {response.text[:500]}")


class GitHubAppClient:
    """Caches an installation token and the App bot login."""

    def __init__(self, owner: str, repo: str) -> None:
        self._owner = owner
        self._repo = repo
        self._token: str | None = None
        self._expires_at: float = 0
        self._bot_login: str | None = None

    def headers(self) -> dict[str, str]:
        return _api_headers(self._installation_token())

    def bot_login(self) -> str:
        if self._bot_login is None:
            app_id, private_key = _credentials()
            response = get(
                f"{_API_BASE}/app",
                headers=_api_headers(build_app_jwt(app_id, private_key)),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            _raise_for_status(response, "lookup")
            slug = response.json().get("slug")
            if not slug:
                raise RuntimeError("GitHub App lookup did not include a slug")
            self._bot_login = f"{slug}[bot]"
            logger.info(f"Commenting on pull requests as {self._bot_login}")
        return self._bot_login

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0

    def _installation_token(self) -> str:
        if self._token and time.time() < self._expires_at - _TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token

        app_id, private_key = _credentials()
        jwt_headers = _api_headers(build_app_jwt(app_id, private_key))
        installation_id = self._installation_id(jwt_headers)
        response = post(
            f"{_API_BASE}/app/installations/{installation_id}/access_tokens",
            headers=jwt_headers,
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        _raise_for_status(response, "token request")
        body = response.json()
        token = body.get("token")
        if not token:
            raise RuntimeError("GitHub App token response did not include a token")

        expires_at = body.get("expires_at")
        if expires_at:
            self._expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
        else:
            self._expires_at = time.time() + 3600
        self._token = token
        logger.info("Refreshed GitHub App installation token")
        return token

    def _installation_id(self, jwt_headers: dict[str, str]) -> str:
        configured = getenv("GITHUB_APP_INSTALLATION_ID", "").strip()
        if configured and configured != "0":
            return configured

        response = get(
            f"{_API_BASE}/repos/{self._owner}/{self._repo}/installation",
            headers=jwt_headers,
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        _raise_for_status(response, f"installation lookup for {self._owner}/{self._repo}")
        installation_id = response.json().get("id")
        if installation_id is None:
            raise RuntimeError(f"GitHub App is not installed on {self._owner}/{self._repo}")
        return str(installation_id)
