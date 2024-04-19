import json
from functools import partial

from requests import Session

from api.host_query_db import get_hosts_to_export
from app import IDENTITY_HEADER
from app import RbacPermission
from app import RbacResourceType
from app import REQUEST_ID_HEADER
from app.auth.identity import create_mock_identity_with_org_id
from app.common import inventory_config
from app.logging import get_logger
from lib.middleware import rbac


logger = get_logger(__name__)


def _handle_rbac_to_export(func, org_id, rbac_request_headers):
    logger.debug("Getting RBAC data")
    rbac_result = rbac(
        RbacResourceType.HOSTS, RbacPermission.READ, org_id=org_id, rbac_request_headers=rbac_request_headers
    )
    filter_func = rbac_result(func)
    filter = filter_func()
    return filter


def create_export(export_svc_data, org_id, operation_args={}, rbac_filter=None):
    config = inventory_config()
    identity = create_mock_identity_with_org_id(org_id)

    exportFormat = export_svc_data["data"]["resource_request"]["format"]
    exportUUID = export_svc_data["data"]["resource_request"]["export_request_uuid"]
    applicationName = export_svc_data["data"]["resource_request"]["application"]
    resourceUUID = export_svc_data["data"]["resource_request"]["uuid"]

    # Need to validate if exportUUID is the correct UUID to be sent
    rbac_request_headers = {
        IDENTITY_HEADER: export_svc_data["data"]["resource_request"][IDENTITY_HEADER],
        REQUEST_ID_HEADER: exportUUID,
    }

    # x-rh-exports-psk must be an env variable
    request_headers = {"x-rh-exports-psk": "testing-a-psk", "content-type": "application/json"}
    session = Session()
    try:
        request_url = (
            f"{config.export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/upload"
        )

        # Change to DEBUG log
        logger.info(f"Trying to get data for org_id: {identity.org_id}")

        data_to_export = _handle_rbac_to_export(
            partial(get_hosts_to_export, identity=identity, export_format=exportFormat),
            org_id=identity.org_id,
            rbac_request_headers=rbac_request_headers,
        )

        if data_to_export:
            # Change to DEBUG log
            logger.info(f"Trying to upload data using URL:{request_url}")
            response = session.post(url=request_url, headers=request_headers, data=json.dumps(data_to_export))
            _handle_export_response(response, exportFormat, exportUUID)
        else:
            # Change to DEBUG log
            logger.info(f"No data found for org_id: {identity.org_id}")
            request_url = (
                f"{config.export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/error"
            )
            response = session.post(
                url=request_url,
                headers=request_headers,
                data=json.dumps({"message": f"No data found for org_id: {identity.org_id}", "error": 404}),
            )
            _handle_export_response(response, exportFormat, exportUUID)
    except Exception as e:
        logger.error(e)
        request_url = (
            f"{config.export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/error"
        )
        response = session.post(
            url=request_url, headers=request_headers, data=json.dumps({"message": str(e), "error": 500})
        )
    finally:
        session.close()


def _handle_export_response(response, exportFormat, exportUUID):
    if response.status_code != 202:
        raise Exception(response.text)
    else:
        logger.info(f"{response.text} for export ID {exportUUID} in {exportFormat.upper()} format")
