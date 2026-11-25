import base64
import json
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dateutil import parser

from jobs.github_app import GitHubAppClient
from jobs.github_app import build_app_jwt
from jobs.github_app import normalize_private_key
from jobs.system_profile_validator import _get_git_response
from jobs.system_profile_validator import _get_latest_self_comment_datetime_for_pr
from jobs.system_profile_validator import _github_app
from jobs.system_profile_validator import _post_git_response
from jobs.system_profile_validator import _rate_limiter
from jobs.system_profile_validator import main


@pytest.fixture
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _response(status_code: int, payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = json.dumps(payload)
    return response


def _reset_rate_limiter() -> None:
    _rate_limiter._remaining = None
    _rate_limiter._reset_timestamp = None
    _rate_limiter._limit = None


def test_normalize_private_key_accepts_raw_escaped_quoted_and_base64(private_key_pem):
    escaped = private_key_pem.replace("\n", "\\n")
    encoded = base64.b64encode(private_key_pem.encode()).decode("utf-8")

    assert normalize_private_key(private_key_pem).strip() == private_key_pem.strip()
    assert normalize_private_key(escaped).strip() == private_key_pem.strip()
    assert normalize_private_key(f'"{escaped}"').strip() == private_key_pem.strip()
    assert normalize_private_key(encoded).strip() == private_key_pem.strip()


def test_normalize_private_key_rejects_empty_and_garbage():
    with pytest.raises(ValueError, match="empty"):
        normalize_private_key("  ")
    with pytest.raises(ValueError, match="PEM"):
        normalize_private_key("not-a-key")


def test_installation_token_uses_configured_id_and_caches_it(monkeypatch, mocker, private_key_pem):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", private_key_pem)
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "99")
    client = GitHubAppClient("RedHatInsights", "insights-host-inventory")
    mock_get = mocker.patch("jobs.github_app.get")
    mock_post = mocker.patch(
        "jobs.github_app.post",
        return_value=_response(201, {"token": "ghs_test", "expires_at": "2099-01-01T00:00:00Z"}),
    )

    assert client.headers()["Authorization"] == "Bearer ghs_test"
    assert client.headers()["Authorization"] == "Bearer ghs_test"

    mock_get.assert_not_called()
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.github.com/app/installations/99/access_tokens"
    assert mock_post.call_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


def test_installation_token_discovers_id_and_refreshes_when_expired(monkeypatch, mocker, private_key_pem):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", private_key_pem)
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "0")
    client = GitHubAppClient("RedHatInsights", "insights-host-inventory")
    mock_get = mocker.patch("jobs.github_app.get", return_value=_response(200, {"id": 42}))
    mock_post = mocker.patch(
        "jobs.github_app.post",
        side_effect=[
            _response(201, {"token": "ghs_old", "expires_at": "2000-01-01T00:00:00Z"}),
            _response(201, {"token": "ghs_new", "expires_at": "2099-01-01T00:00:00Z"}),
        ],
    )

    assert client.headers()["Authorization"] == "Bearer ghs_old"
    assert client.headers()["Authorization"] == "Bearer ghs_new"

    assert mock_get.call_args.args[0] == (
        "https://api.github.com/repos/RedHatInsights/insights-host-inventory/installation"
    )
    assert mock_post.call_count == 2


def test_signed_jwt_uses_the_app_id_as_issuer(private_key_pem):
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)

    app_jwt = build_app_jwt("12345", private_key_pem)
    claims = jwt.decode(app_jwt, private_key.public_key(), algorithms=["RS256"])

    assert claims["iss"] == "12345"


def test_bot_login_uses_app_slug(monkeypatch, mocker, private_key_pem):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", private_key_pem)
    client = GitHubAppClient("RedHatInsights", "insights-host-inventory")
    mock_get = mocker.patch("jobs.github_app.get", return_value=_response(200, {"slug": "bugkiller-agent"}))

    assert client.bot_login() == "bugkiller-agent[bot]"
    assert client.bot_login() == "bugkiller-agent[bot]"
    mock_get.assert_called_once()


def test_headers_require_github_app_credentials(monkeypatch):
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    client = GitHubAppClient("RedHatInsights", "insights-host-inventory")

    with pytest.raises(RuntimeError, match="GITHUB_APP_ID"):
        client.headers()


def _stub_installation_tokens(monkeypatch, mocker, private_key_pem: str, tokens: list[str]) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", private_key_pem)
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "99")
    _github_app.invalidate()
    mocker.patch(
        "jobs.github_app.post",
        side_effect=[_response(201, {"token": token, "expires_at": "2099-01-01T00:00:00Z"}) for token in tokens],
    )


def test_get_git_response_refreshes_token_on_401(mocker, monkeypatch, private_key_pem):
    _reset_rate_limiter()
    _stub_installation_tokens(monkeypatch, mocker, private_key_pem, ["ghs_rejected", "ghs_fresh"])
    unauthorized = MagicMock(status_code=401, headers={}, text="Bad credentials", content=b"")
    success = MagicMock(status_code=200, headers={"X-RateLimit-Remaining": "10", "X-RateLimit-Limit": "5000"})
    success.content = b'{"ok": true}'
    mock_get = mocker.patch("jobs.system_profile_validator.get", side_effect=[unauthorized, success])

    assert _get_git_response("/x") == {"ok": True}
    assert [call.kwargs["headers"]["Authorization"] for call in mock_get.call_args_list] == [
        "Bearer ghs_rejected",
        "Bearer ghs_fresh",
    ]


def test_post_retries_once_after_401(mocker, monkeypatch, private_key_pem):
    _stub_installation_tokens(monkeypatch, mocker, private_key_pem, ["ghs_rejected", "ghs_fresh"])
    denied = MagicMock(status_code=401)
    posted = MagicMock(status_code=201)
    mock_post = mocker.patch("jobs.system_profile_validator.post", side_effect=[denied, posted])

    assert _post_git_response("/repos/o/r/issues/1/comments", "hello") is posted
    assert [call.kwargs["headers"]["Authorization"] for call in mock_post.call_args_list] == [
        "Bearer ghs_rejected",
        "Bearer ghs_fresh",
    ]


def _comment(login: str | None, created_at: str, body: str) -> dict:
    return {"user": None if login is None else {"login": login}, "created_at": created_at, "body": body}


_RESULTS_BODY = "Here are the System Profile validation results using Prod data.\nsatellite:\n\tPass: 1\n"
_PARSE_ERROR_BODY = (
    "An error occurred while trying to parse the schema in this PR. Please verify the syntax and formatting."
)


def test_self_comment_ignores_unrelated_bugkiller_comments(mocker):
    mocker.patch("jobs.system_profile_validator._github_app.bot_login", return_value="bugkiller-agent[bot]")
    mocker.patch(
        "jobs.system_profile_validator._get_git_response",
        return_value=[
            _comment("dippy-bot", "2026-01-03T00:00:00Z", _RESULTS_BODY),
            _comment(None, "2026-01-04T00:00:00Z", _RESULTS_BODY),
            _comment("bugkiller-agent[bot]", "2026-01-05T00:00:00Z", "Implemented the spec and pushed the branch."),
            _comment("someone", "2026-01-06T00:00:00Z", _RESULTS_BODY),
        ],
    )

    found = _get_latest_self_comment_datetime_for_pr("RedHatInsights", "insights-host-inventory", "1")

    assert found == parser.isoparse("2026-01-03T00:00:00Z")


def test_self_comment_uses_latest_validation_comment_from_either_login(mocker):
    mocker.patch("jobs.system_profile_validator._github_app.bot_login", return_value="bugkiller-agent[bot]")
    mocker.patch(
        "jobs.system_profile_validator._get_git_response",
        return_value=[
            _comment("dippy-bot", "2026-01-03T00:00:00Z", _RESULTS_BODY),
            _comment("bugkiller-agent[bot]", "2026-01-05T00:00:00Z", _RESULTS_BODY),
            _comment("bugkiller-agent[bot]", "2026-01-06T00:00:00Z", _PARSE_ERROR_BODY),
        ],
    )

    found = _get_latest_self_comment_datetime_for_pr("RedHatInsights", "insights-host-inventory", "1")

    assert found == parser.isoparse("2026-01-06T00:00:00Z")


def test_main_skips_replica_and_requires_credentials_otherwise(monkeypatch):
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)

    with pytest.raises(SystemExit) as replica_exit:
        main(MagicMock(), MagicMock(replica_namespace=True))
    assert replica_exit.value.code == 0

    with pytest.raises(SystemExit) as missing_exit:
        main(MagicMock(), MagicMock(replica_namespace=False))
    assert missing_exit.value.code == 1
