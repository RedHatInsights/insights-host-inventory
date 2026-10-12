from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from dynaconf.base import Settings
from iqe_library.http import create_session_from_config
from requests import Session


@dataclass
class TestApp:
    __test__ = False  # Otherwise pytest would think that this class includes tests
    config: Settings
    api_session: Session
    base_url: str


@contextmanager
def create_test_app(config: Settings, *, user: str | None = None, auth_type: str | None = None) -> Iterator[TestApp]:
    """Own one independent session for the lifetime of an app, without changing config."""
    if auth_type is None:
        auth_type = config.http.default_auth_type
    with create_session_from_config(config, user=user, auth_type=auth_type) as session:
        yield TestApp(config=config, api_session=session, base_url=config.base_url)
