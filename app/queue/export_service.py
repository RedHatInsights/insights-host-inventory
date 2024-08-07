import json
from http import HTTPStatus

from requests import Session
from requests.adapters import HTTPAdapter

from api.host_query_db import get_hosts_to_export
from app import IDENTITY_HEADER
from app import RbacPermission
from app import RbacResourceType
from app import REQUEST_ID_HEADER
from app.auth.identity import create_mock_identity_with_org_id
from app.logging import get_logger
from lib import metrics
from lib.middleware import get_rbac_filter
from utils.json_to_csv import json_arr_to_csv

logger = get_logger(__name__)

HEADER_CONTENT_TYPE = {"json": "application/json", "csv": "text/csv"}


@metrics.create_export_processing_time.time()
def create_export(export_svc_data, org_id, inventory_config, operation_args={}, rbac_filter={}):
    identity = create_mock_identity_with_org_id(org_id)

    metrics.create_export_count.inc()
    logger.info("Creating export for HBI")

    exportFormat = export_svc_data["data"]["resource_request"]["format"]
    exportUUID = export_svc_data["data"]["resource_request"]["export_request_uuid"]
    applicationName = export_svc_data["data"]["resource_request"]["application"]
    resourceUUID = export_svc_data["data"]["resource_request"]["uuid"]

    rbac_request_headers = {
        IDENTITY_HEADER: export_svc_data["data"]["resource_request"]["x_rh_identity"],
        REQUEST_ID_HEADER: str(exportUUID),
    }

    # x-rh-exports-psk must be an env variable
    request_headers = {
        "x-rh-exports-psk": inventory_config.export_service_token,
        "content-type": HEADER_CONTENT_TYPE[exportFormat.lower()],
    }
    session = Session()
    try:
        export_service_endpoint = inventory_config.export_service_endpoint
        request_url = f"{export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/upload"

        session.mount(request_url, HTTPAdapter(max_retries=3))

        logger.info(f"Trying to get data for org_id: {identity.org_id}")

        rbac_filter = get_rbac_filter(
            RbacResourceType.HOSTS, RbacPermission.READ, identity=identity, rbac_request_headers=rbac_request_headers
        )
        data_to_export = get_hosts_to_export(
            identity,
            export_format=exportFormat,
            rbac_filter=rbac_filter,
            batch_size=inventory_config.export_svc_batch_size,
        )

        if data_to_export:
            logger.debug(f"Trying to upload data using URL:{request_url}")
            logger.info(
                f"{len(data_to_export)} hosts will be exported (format: {exportFormat}) for org_id {identity.org_id}"
            )
            response = session.post(
                url=request_url, headers=request_headers, data=_format_export_data(data_to_export, exportFormat)
            )
            _handle_export_response(response, exportFormat, exportUUID)
            return True
        else:
            logger.debug(f"No data found for org_id: {identity.org_id}")
            request_url = (
                f"{export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/error"
            )
            response = session.post(
                url=request_url,
                headers=request_headers,
                data=json.dumps({"message": f"No data found for org_id: {identity.org_id}", "error": 404}),
            )
            _handle_export_response(response, exportFormat, exportUUID)
            return False
    except Exception as e:
        logger.error(e)
        request_url = f"{export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/error"
        response = session.post(
            url=request_url, headers=request_headers, data=json.dumps({"message": str(e), "error": 500})
        )
        return False
    finally:
        session.close()


# This function is used by create_export, needs improvement
def _handle_export_response(response, exportFormat, exportUUID):
    if response.status_code != HTTPStatus.ACCEPTED:
        raise Exception(response.text)
    elif response.text != "":
        logger.info(f"{response.text} for export ID {exportUUID} in {exportFormat.upper()} format")


def _format_export_data(data, exportFormat):
    if exportFormat == "json":
        return json.dumps(data)
    elif exportFormat == "csv":
        return json_arr_to_csv(data)
