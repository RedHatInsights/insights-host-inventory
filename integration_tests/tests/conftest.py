import logging
import os
from typing import Any

import pytest
from pytest import Config as PytestConfig
from requests import Response
from requests import Session

from integration_tests.config import ENV_VAR_AUTH_TYPE
from integration_tests.config import BasicAuth
from integration_tests.config import Config
from integration_tests.config import User
from integration_tests.config import load_config
from integration_tests.utils.app import TestApp

logger = logging.getLogger(__name__)


_LOG_FORMAT = "%(levelname)s %(asctime)s %(filename)s:%(lineno)d %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def pytest_configure(config: PytestConfig) -> None:
    config.option.log_cli_level = "INFO"
    config.option.log_cli_format = _LOG_FORMAT
    config.option.log_cli_date_format = _LOG_DATE_FORMAT


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config()


def _get_auth(user: User, auth_type: str) -> BasicAuth:
    auth = getattr(user, auth_type, None)
    if auth is None:
        raise ValueError(f"User does not have auth type '{auth_type}' configured")
    return auth


def _apply_auth(session: Session, auth: BasicAuth) -> None:
    session.auth = (auth.username, auth.password.get_secret_value())


@pytest.fixture(scope="session")
def api_session(config: Config) -> Session:
    auth_type = os.environ.get(ENV_VAR_AUTH_TYPE, config.default_auth_type)
    user = config.users[config.default_user]
    auth = _get_auth(user, auth_type)

    session = Session()
    session.headers["Content-Type"] = "application/json"
    _apply_auth(session, auth)

    if config.proxy:
        session.proxies = {"http": config.proxy, "https": config.proxy}

    def _log_response(response: Response, *args: Any, **kwargs: Any) -> None:
        method = response.request.method
        url = response.request.url
        request_id = response.headers.get("x-rh-insights-request-id")
        logger.info(f"{method} {url} (request_id={request_id}) -> {response.status_code}")

    session.hooks["response"].append(_log_response)

    return session


@pytest.fixture(scope="session")
def test_app(config: Config, api_session: Session) -> TestApp:
    return TestApp(config=config, api_session=api_session)
