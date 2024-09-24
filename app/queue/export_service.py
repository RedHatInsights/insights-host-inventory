import json
from http import HTTPStatus
from typing import List
from typing import Tuple
from uuid import UUID

from requests import Response
from requests import Session
from requests.adapters import HTTPAdapter

from api.host_query_db import get_hosts_to_export
from app import IDENTITY_HEADER
from app import RbacPermission
from app import RbacResourceType
from app import REQUEST_ID_HEADER
from app.auth.identity import from_auth_header
from app.auth.identity import Identity
from app.config import Config
from app.logging import get_logger
from lib import metrics
from lib.middleware import get_rbac_filter
from utils.json_to_csv import json_arr_to_csv

logger = get_logger(__name__)

HEADER_CONTENT_TYPE = {"json": "application/json", "csv": "text/csv"}


def extract_export_svc_data(export_svc_data: dict) -> Tuple[str, UUID, str, str, str]:
    exportFormat = export_svc_data["data"]["resource_request"]["format"]
    exportUUID = export_svc_data["data"]["resource_request"]["export_request_uuid"]
    applicationName = export_svc_data["data"]["resource_request"]["application"]
    resourceUUID = export_svc_data["data"]["resource_request"]["uuid"]
    x_rh_identity = export_svc_data["data"]["resource_request"]["x_rh_identity"]

    return exportFormat, exportUUID, applicationName, resourceUUID, x_rh_identity


def build_headers(
    x_rh_identity: str, exportUUID: UUID, inventory_config: Config, exportFormat: str
) -> Tuple[dict, dict]:
    rbac_request_headers = {
        IDENTITY_HEADER: x_rh_identity,
        REQUEST_ID_HEADER: str(exportUUID),
    }

    # x-rh-exports-psk must be an env variable
    request_headers = {
        "x-rh-exports-psk": inventory_config.export_service_token,
        "content-type": HEADER_CONTENT_TYPE[exportFormat.lower()],
    }

    return rbac_request_headers, request_headers


def get_host_list(identity: Identity, exportFormat: str, rbac_filter: dict, inventory_config: Config) -> List[dict]:
    host_data = list(
        get_hosts_to_export(
            identity,
            export_format=exportFormat,
            rbac_filter=rbac_filter,
            batch_size=inventory_config.export_svc_batch_size,
        )
    )

    return host_data


@metrics.create_export_processing_time.time()
def create_export(
    export_svc_data: dict,
    base64_x_rh_identity: str,
    inventory_config: Config,
    operation_args={},
    rbac_filter: dict = {},
) -> bool:
    identity = from_auth_header(base64_x_rh_identity)

    metrics.create_export_count.inc()
    logger.info("Creating export for HBI")

    exportFormat, exportUUID, applicationName, resourceUUID, x_rh_identity = extract_export_svc_data(export_svc_data)

    rbac_request_headers, request_headers = build_headers(x_rh_identity, exportUUID, inventory_config, exportFormat)

    allowed, rbac_filter = get_rbac_filter(
        RbacResourceType.HOSTS, RbacPermission.READ, identity=identity, rbac_request_headers=rbac_request_headers
    )

    export_service_endpoint = inventory_config.export_service_endpoint

    export_created = False
    session = Session()

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
        # create a generator with serialized host data
        host_data = get_host_list(identity, exportFormat, rbac_filter, inventory_config)

        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "upload"
        )

        session.mount(request_url, HTTPAdapter(max_retries=3))

        logger.info(f"Trying to get data for org_id: {identity.org_id}")

        if host_data:
            logger.debug(f"Trying to upload data using URL:{request_url}")
            logger.info(
                f"{len(host_data)} hosts will be exported (format: {exportFormat}) for org_id {identity.org_id}"
            )
            response = session.post(
                url=request_url, headers=request_headers, data=_format_export_data(host_data, exportFormat)
            )
            _handle_export_response(response, exportUUID, exportFormat)
            export_created = True
        else:
            logger.debug(f"No data found for org_id: {identity.org_id}")
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
    except Exception as e:
        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
        )
        _handle_export_error(str(e), 500, request_url, session, request_headers, exportUUID, exportFormat)
        export_created = False
    finally:
        session.close()
        return export_created


def _build_export_request_url(
    export_service_endpoint: str, exportUUID: str, applicationName: str, resourceUUID: str, request_type: str
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
    response = session.post(
        url=request_url,
        headers=request_headers,
        data=json.dumps({"message": str(error_message), "error": status_code}),
    )
    _handle_export_response(response, exportUUID, exportFormat)


# This function is used by create_export, needs improvement
def _handle_export_response(response: Response, exportUUID: UUID, exportFormat: str):
    if response.status_code != HTTPStatus.ACCEPTED:
        raise Exception(response.text)
    elif response.text != "":
        logger.info(f"{response.text} for export ID {str(exportUUID)} in {exportFormat.upper()} format")


def _format_export_data(data: dict, exportFormat: str) -> str:
    if exportFormat == "json":
        return json.dumps(data)
    elif exportFormat == "csv":
        return json_arr_to_csv(data)
