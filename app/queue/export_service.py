from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from http import HTTPStatus
from uuid import UUID

from requests import Response
from requests import Session
from requests.adapters import HTTPAdapter

from api.host_query_db import get_hosts_to_export
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app.auth.identity import Identity
from app.auth.identity import from_auth_header
from app.auth.rbac import KesselResourceTypes
from app.config import Config
from app.exceptions import InventoryException
from app.logging import get_logger
from app.serialization import _EXPORT_SERVICE_FIELDS
from lib import metrics
from lib.kessel import get_kessel_oauth2_credentials
from lib.middleware import resolve_permission
from utils.json_to_csv import export_csv_header
from utils.json_to_csv import export_host_to_csv_row

logger = get_logger(__name__)

HEADER_CONTENT_TYPE = {"json": "application/json; charset=utf-8", "csv": "text/csv; charset=utf-8"}


class _StreamingExportBody:
    def __init__(self, host_iter: Iterator[dict], export_format: str):
        self._host_iter = host_iter
        self._export_format = export_format.lower()
        self.host_count = 0

    def __iter__(self):
        if self._export_format == "json":
            yield b"["
            first = True
            for host in self._host_iter:
                self.host_count += 1
                if not first:
                    yield b","
                first = False
                yield json.dumps(host).encode("utf-8")
            yield b"]"
        elif self._export_format == "csv":
            yield export_csv_header(_EXPORT_SERVICE_FIELDS).encode("utf-8")
            for host in self._host_iter:
                self.host_count += 1
                yield export_host_to_csv_row(host, _EXPORT_SERVICE_FIELDS).encode("utf-8")
        else:
            raise ValueError(f"Unsupported export format: {self._export_format}")


def extract_export_svc_data(export_svc_data: dict) -> tuple[str, UUID, str, str, str]:
    exportFormat = export_svc_data["data"]["resource_request"]["format"]
    exportUUID = export_svc_data["data"]["resource_request"]["export_request_uuid"]
    applicationName = export_svc_data["data"]["resource_request"]["application"]
    resourceUUID = export_svc_data["data"]["resource_request"]["uuid"]
    x_rh_identity = export_svc_data["data"]["resource_request"]["x_rh_identity"]

    return exportFormat, exportUUID, applicationName, resourceUUID, x_rh_identity


def _get_export_service_access_token(inventory_config: Config) -> str:
    """Get an OAuth2 workload-identity access token for authenticated export-service calls."""
    oauth_client = get_kessel_oauth2_credentials(inventory_config)
    token_response = oauth_client.get_token()
    return token_response.access_token


def build_headers(
    x_rh_identity: str, exportUUID: UUID, inventory_config: Config, exportFormat: str
) -> tuple[dict, dict]:
    rbac_request_headers = {
        IDENTITY_HEADER: x_rh_identity,
        REQUEST_ID_HEADER: str(exportUUID),
    }

    request_headers = {
        "content-type": HEADER_CONTENT_TYPE[exportFormat.lower()],
    }

    if inventory_config.export_service_endpoint_authenticated:
        # V2 endpoint requires workload identity -- attach an OAuth2 Bearer token from the Kessel SDK.
        access_token = _get_export_service_access_token(inventory_config)
        request_headers["Authorization"] = f"Bearer {access_token}"
    else:
        # Unauthenticated (in-cluster) endpoint -- fall back to the shared export-service PSK.
        request_headers["x-rh-exports-psk"] = inventory_config.export_service_token

    return rbac_request_headers, request_headers


def _non_empty_hosts_iter(
    identity: Identity, rbac_filter: dict | None, inventory_config: Config
) -> Iterator[dict] | None:
    """Return a non-empty host iterator, or None if there are no hosts to export."""
    host_iter = get_hosts_to_export(
        identity,
        rbac_filter=rbac_filter,
        batch_size=inventory_config.export_svc_batch_size,
    )
    first_host = next(host_iter, None)
    if first_host is None:
        return None
    return itertools.chain([first_host], host_iter)


@metrics.create_export_processing_time.time()
def create_export(
    export_svc_data: dict,
    base64_x_rh_identity: str,
    inventory_config: Config,
    operation_args: dict | None = None,
    rbac_filter: dict | None = None,
) -> bool:
    if operation_args is None:
        operation_args = {}
    if rbac_filter is None:
        rbac_filter = {}

    identity = from_auth_header(base64_x_rh_identity)

    metrics.create_export_count.inc()
    logger.info("Creating export for HBI")

    exportFormat, exportUUID, applicationName, resourceUUID, x_rh_identity = extract_export_svc_data(export_svc_data)

    rbac_request_headers, request_headers = build_headers(x_rh_identity, exportUUID, inventory_config, exportFormat)

    allowed, rbac_filter = resolve_permission(
        identity, KesselResourceTypes.HOST.view, rbac_request_headers=rbac_request_headers
    )

    export_service_endpoint = inventory_config.export_service_endpoint

    export_created = False
    session = Session()
    # Honor the per-endpoint CA certificate from the V2 dependency endpoint; fall back to system trust.
    session.verify = inventory_config.export_service_endpoint_ca_certificate or True

    if not allowed:
        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
        )
        _handle_export_error(
            "You don't have the permission to access the requested resource.",
            403,
            request_url,
            session,
            request_headers,
            exportUUID,
            exportFormat,
        )
        session.close()
        return export_created

    try:
        hosts_iter = _non_empty_hosts_iter(identity, rbac_filter, inventory_config)

        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "upload"
        )

        session.mount(request_url, HTTPAdapter(max_retries=3))

        logger.info(f"Trying to get data for org_id: {identity.org_id}")

        if hosts_iter is not None:
            logger.debug(f"Trying to upload data using URL:{request_url}")
            export_body = _StreamingExportBody(hosts_iter, exportFormat)
            response = session.post(
                url=request_url,
                headers=request_headers,
                data=export_body,
            )
            logger.info(
                f"{export_body.host_count} hosts exported (format: {exportFormat}) for org_id {identity.org_id}"
            )
            _handle_export_response(response, exportUUID, exportFormat)
            export_created = True
        else:
            logger.info(f"No hosts to export for org_id: {identity.org_id}")
            request_url = _build_export_request_url(
                export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
            )
            response = session.post(
                url=request_url,
                headers=request_headers,
                data=json.dumps({"message": f"No data found for org_id: {identity.org_id}", "error": 404}),
            )
            _handle_export_response(response, exportUUID, exportFormat)
            export_created = False
    except InventoryException as e:
        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
        )
        _handle_export_error(str(e), 500, request_url, session, request_headers, exportUUID, exportFormat)
        export_created = False
    finally:
        session.close()

    return export_created


def _build_export_request_url(
    export_service_endpoint: str, exportUUID: UUID, applicationName: str, resourceUUID: str, request_type: str
) -> str:
    return f"{export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/{request_type}"


def _handle_export_error(
    error_message: str,
    status_code: int,
    request_url: str,
    session: Session,
    request_headers: dict,
    exportUUID: UUID,
    exportFormat: str,
):
    logger.error(error_message)
    try:
        response = session.post(
            url=request_url,
            headers=request_headers,
            data=json.dumps({"message": error_message, "error": status_code}),
        )
        _handle_export_response(response, exportUUID, exportFormat)
    except Exception:
        logger.exception(f"Failed to report export error to export-service for export {exportUUID}")


def _handle_export_response(response: Response, exportUUID: UUID, exportFormat: str):
    if response.status_code == HTTPStatus.ACCEPTED:
        if response.text != "":
            logger.info(f"{response.text} for export ID {str(exportUUID)} in {exportFormat.upper()} format")
    elif "already been processed" in (response.text or "").lower():
        logger.warning(f"Export {exportUUID} was already processed (duplicate delivery); treating as success")
    else:
        raise InventoryException(detail=response.text)


def _format_export_data(data: list[dict], exportFormat: str) -> str:
    """Materialize export payload for tests and small fixtures."""
    body = _StreamingExportBody(iter(data), exportFormat)
    return b"".join(body).decode("utf-8")
