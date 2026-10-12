from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from dynaconf.base import Settings
from iqe_library.http import create_session_from_config
from requests import Session

if TYPE_CHECKING:
    from integration_tests.utils.archive import ArchiveUploader
    from integration_tests.utils.rest_api import InventoryAPI


@dataclass
class TestApp:
    __test__ = False  # Otherwise pytest would think that this class includes tests
    config: Settings
    api_session: Session
    base_url: str
    uploader: ArchiveUploader = field(init=False)
    hbi_api: InventoryAPI = field(init=False)

    def __post_init__(self) -> None:
        from integration_tests.utils.archive import ArchiveUploader
        from integration_tests.utils.rest_api import InventoryAPI

        self.uploader = ArchiveUploader(test_app=self)
        self.hbi_api = InventoryAPI(test_app=self)


@contextmanager
def create_test_app(config: Settings, *, user: str | None = None, auth_type: str | None = None) -> Iterator[TestApp]:
    """Own one independent session for the lifetime of an app, without changing config."""
    if auth_type is None:
        auth_type = config.http.default_auth_type
    base_url = config.cert_base_url if auth_type == "cert" else config.base_url
    with create_session_from_config(config, user=user, auth_type=auth_type) as session:
        yield TestApp(config=config, api_session=session, base_url=base_url)
