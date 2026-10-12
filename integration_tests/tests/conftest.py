import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dynaconf.base import Settings
from iqe_library.config import load_config
from pytest import Config as PytestConfig
from requests import Session

from integration_tests.utils.app import TestApp
from integration_tests.utils.app import create_test_app

_LOG_FORMAT = "%(levelname)s %(asctime)s %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def pytest_configure(config: PytestConfig) -> None:
    config.option.log_cli_level = "INFO"
    config.option.log_cli_format = _LOG_FORMAT
    config.option.log_cli_date_format = _LOG_DATE_FORMAT


@pytest.fixture(scope="session")
def config() -> Settings:
    config_path = Path(os.environ.get("HBI_TEST_CONFIG_PATH", Path(__file__).parents[1] / "config.yaml"))
    return load_config(config_path)


@pytest.fixture(scope="session")
def test_app(config: Settings) -> Iterator[TestApp]:
    with create_test_app(config) as app:
        yield app


@pytest.fixture(scope="session")
def api_session(test_app: TestApp) -> Session:
    return test_app.api_session
