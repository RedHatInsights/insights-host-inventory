from http import HTTPStatus

from requests import Session

from api.host_query_db import get_hosts_to_export
from app import IDENTITY_HEADER
from app import RbacPermission
from app import RbacResourceType
from app import REQUEST_ID_HEADER
from app.auth.identity import create_mock_identity_with_org_id
from app.common import inventory_config
from app.logging import get_logger
from lib import metrics
from lib.middleware import get_rbac_filter

logger = get_logger(__name__)

EXPORT_SERVICE_SYSTEMS_RESOURCE = "urn:redhat:application:inventory:export:systems"


@metrics.create_export_processing_time.time()
def create_export(export_svc_data, org_id, operation_args={}, rbac_filter={}):
    config = inventory_config()
    identity = create_mock_identity_with_org_id(org_id)

    metrics.create_export_count.inc()
    logger.info("Creating export for HBI")

    exportFormat = export_svc_data["data"]["resource_request"]["format"]
    exportUUID = export_svc_data["data"]["resource_request"]["export_request_uuid"]
    applicationName = export_svc_data["data"]["resource_request"]["application"]
    resourceUUID = export_svc_data["data"]["resource_request"]["uuid"]

    rbac_request_headers = {
        IDENTITY_HEADER: export_svc_data["data"]["resource_request"]["x_rh_identity"],
        REQUEST_ID_HEADER: exportUUID,
    }

    session = Session()
    try:
        request_url = {
            f"{config.export_service_endpoint}/app/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/upload"
        }

        logger.info(f"Trying to get data for org_id: {identity.org_id}")

        rbac_filter = get_rbac_filter(
            RbacResourceType.HOSTS, RbacPermission.READ, identity=identity, rbac_request_headers=rbac_request_headers
        )
        data_to_export = get_hosts_to_export(identity, export_format=exportFormat, rbac_filter=rbac_filter)

        if data_to_export:
            # todo(gchamoul):
            # Next Step will done here:
            # - POST to export service with the data to be exported
            logger.info(
                f"{len(data_to_export)} hosts will be exported (format: {exportFormat}) for org_id {identity.org_id}"
            )
            logger.info(f"Trying to upload data using URL: {request_url}")
            return True
        else:
            # todo(gchamoul):
            # POST to export service and handle an 404 error properly
            logger.info(f"No data found for org_id: {identity.org_id}")
            return False
    except Exception as e:
        logger.error(e)
        # todo(gchamoul):
        # POST to export service and handle an 500 error properly
        return False
    finally:
        session.close()


# This function is used by create_export, needs improvement
def _handle_export_response(response, exportFormat, exportUUID):
    if response.status_code != HTTPStatus.ACCEPTED:
        raise Exception(response.text)
    else:
        logger.info(f"{response.text} for export ID {exportUUID} in {exportFormat.upper()} format")
