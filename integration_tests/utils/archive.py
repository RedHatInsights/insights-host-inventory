import logging
import re
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from time import sleep
from typing import Any
from uuid import uuid4

from requests import Response
from requests.exceptions import HTTPError

from integration_tests.utils.app import TestApp

_ARCHIVES_DIR = Path(__file__).parent.parent / "data" / "archives"

_INSIGHTS_ID_PATH = "data/etc/insights-client/machine-id"
_RHSM_ID_PATH = "data/insights_commands/subscription-manager_identity"
_HOSTNAME_PATH = "data/insights_commands/hostname_-f"

DEFAULT_ARCHIVE = "rhel94.tar.gz"

logger = logging.getLogger(__name__)


@dataclass
class HostArchiveData:
    insights_id: str
    subscription_manager_id: str
    fqdn: str

    @classmethod
    def random(cls, fqdn_prefix: str = "hbi-test") -> "HostArchiveData":
        insights_id = str(uuid4())
        return cls(
            insights_id=insights_id,
            subscription_manager_id=str(uuid4()),
            fqdn=f"{fqdn_prefix}.{insights_id}",
        )


def prepare_archive(
    host_data: HostArchiveData,
    source_archive_name: str = DEFAULT_ARCHIVE,
) -> Path:
    """Extract an archive, replace identifiers, and re-pack it.

    Returns the path to the new tar.gz and the HostArchiveData with the values used.
    """
    source = _ARCHIVES_DIR / source_archive_name

    work_dir = Path(mkdtemp())

    with tarfile.open(source, "r:gz") as tar:
        tar.extractall(work_dir, filter="data")

    top_dirs = list(work_dir.iterdir())
    archive_dir = top_dirs[0]

    # insights_id
    insights_id_file = archive_dir / _INSIGHTS_ID_PATH
    insights_id_file.write_text(host_data.insights_id)

    # subscription_manager_id and name in subscription-manager identity output
    rhsm_id_file = archive_dir / _RHSM_ID_PATH
    content = rhsm_id_file.read_text()
    content = re.sub(r"(?<=^system identity: ).+", host_data.subscription_manager_id, content, flags=re.MULTILINE)
    content = re.sub(r"(?<=^name: ).+", host_data.fqdn, content, flags=re.MULTILINE)
    rhsm_id_file.write_text(content)

    # fqdn
    hostname_file = archive_dir / _HOSTNAME_PATH
    hostname_file.write_text(host_data.fqdn)

    new_archive = work_dir / f"{host_data.fqdn}.tar.gz"
    with tarfile.open(new_archive, "w:gz") as tar:
        tar.add(archive_dir, arcname=archive_dir.name)

    return new_archive


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
        self.upload_url = f"{test_app.config.ingress_api_url}/upload"

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
        source_archive: str = DEFAULT_ARCHIVE,
        wait_for_created: bool = True,
    ) -> HostArchiveData:
        host_data = host_data or HostArchiveData.random()
        archive = prepare_archive(host_data, source_archive)

        response = self.upload(archive)
        if response.status_code != 201:
            try:
                response.raise_for_status()
            except HTTPError as err:
                raise ArchiveUploadError(archive, response.status_code, response.text) from err
            raise ArchiveUploadError(archive, response.status_code, response.text)

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
