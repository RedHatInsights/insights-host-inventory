from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from requests import Session

from integration_tests.config import Config

if TYPE_CHECKING:
    from integration_tests.utils.archive import ArchiveUploader
    from integration_tests.utils.rest_api import InventoryAPI


@dataclass
class TestApp:
    __test__ = False  # Otherwise pytest would think that this class includes tests
    config: Config
    api_session: Session
    uploader: ArchiveUploader = field(init=False)
    hbi_api: InventoryAPI = field(init=False)

    def __post_init__(self) -> None:
        from integration_tests.utils.archive import ArchiveUploader
        from integration_tests.utils.rest_api import InventoryAPI

        self.uploader = ArchiveUploader(test_app=self)
        self.hbi_api = InventoryAPI(test_app=self)
