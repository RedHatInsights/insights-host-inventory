import logging
from collections.abc import Callable
from pathlib import Path
from shutil import rmtree
from time import sleep
from typing import Any

from iqe_library.archive import DEFAULT_ARCHIVE
from iqe_library.archive import HostArchiveData
from iqe_library.archive import prepare_archive
from requests import Response
from requests.exceptions import HTTPError

from integration_tests.utils.app import TestApp

logger = logging.getLogger(__name__)


class ArchiveUploadError(Exception):
    def __init__(self, archive: Path, status_code: int, response_body: str = ""):
        self.archive = archive
        self.status_code = status_code
        self.response_body = response_body
        message = f"Archive upload failed: {archive.name}, status={status_code}"
        if response_body:
            message += f"\nResponse body:\n{response_body}"
        super().__init__(message)


class HostLookupError(Exception):
    def __init__(self, insights_id: str, message: str):
        super().__init__(message, insights_id)


def _poll_for_host(
    insights_id: str,
    fetch: Callable[[], list[dict[str, Any]]],
    endpoint_name: str,
    *,
    retries: int,
    timeout: float,
) -> dict[str, Any]:
    for attempt in range(1, retries + 1):
        logger.info(f"Attempt {attempt} to get the created host via {endpoint_name}")
        results = fetch()

        if len(results) > 1:
            raise HostLookupError(
                insights_id, f"Multiple hosts with insights_id={insights_id} found via {endpoint_name}"
            )
        if len(results) == 1:
            return results[0]

        logger.info(f"Waiting {timeout}s for the next attempt")
        sleep(timeout)

    raise HostLookupError(
        insights_id, f"Could not get created host with insights_id={insights_id} via {endpoint_name}"
    )


class ArchiveUploader:
    def __init__(self, test_app: TestApp):
        self._test_app = test_app
        self.session = test_app.api_session
        self.base_url = f"{test_app.base_url}{test_app.config.ingress_api_base_path}"
        self.upload_url = f"{self.base_url}/upload"

    def upload(
        self,
        archive_path: Path,
        content_type: str = "application/vnd.redhat.advisor.collection+tgz",
    ) -> Response:
        """Upload a tar.gz archive to the ingress service."""
        with open(archive_path, "rb") as f:
            response = self.session.post(
                self.upload_url,
                files={"file": ("archive.tar.gz", f, content_type)},
                headers={"Content-Type": None},  # let requests set the multipart boundary
            )
        return response

    def create_host(
        self,
        host_data: HostArchiveData | None = None,
        *,
        source_archive: str | Path = DEFAULT_ARCHIVE,
        wait_for_created: bool = True,
    ) -> HostArchiveData:
        host_data = host_data or HostArchiveData.random(fqdn_prefix="hbi-test")
        archive = prepare_archive(host_data, source_archive)

        try:
            response = self.upload(archive)
            if response.status_code != 201:
                try:
                    response.raise_for_status()
                except HTTPError as err:
                    raise ArchiveUploadError(archive, response.status_code, response.text) from err
                raise ArchiveUploadError(archive, response.status_code, response.text)
        finally:
            rmtree(archive.parent)

        if wait_for_created:
            self.wait_for_host_created(host_data.insights_id)

        return host_data

    def wait_for_host_created(self, insights_id: str, *, retries: int = 100, timeout: float = 0.5) -> dict[str, Any]:
        # Wait until the host is retrievable via GET /hosts
        host = _poll_for_host(
            insights_id,
            fetch=lambda: self._test_app.hbi_api.get_host_list(insights_id=insights_id),
            endpoint_name="GET /hosts",
            retries=retries,
            timeout=timeout,
        )

        # Wait until the host is retrievable via GET /hosts/<host_id>
        host_id = host["id"]
        _poll_for_host(
            insights_id,
            fetch=lambda: self._test_app.hbi_api.get_hosts_by_id([host_id]),
            endpoint_name=f"GET /hosts/{host_id}",
            retries=retries,
            timeout=timeout,
        )

        return host
