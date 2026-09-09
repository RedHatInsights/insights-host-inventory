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
from api.views_validation import VALID_HOST_FILTER_KEYS
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app.auth.identity import Identity
from app.auth.identity import from_auth_header
from app.auth.rbac import KesselResourceTypes
from app.config import Config
from app.exceptions import InventoryException
from app.logging import get_logger
from app.models.host_app_data import get_app_data_models
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import ALWAYS_INCLUDED_EXPORT_FIELDS
from app.serialization import CORE_VIEW_FIELDS_TO_EXPORT_FIELDS
from lib import metrics
from lib.kessel import get_kessel_oauth2_credentials
from lib.middleware import resolve_permission
from lib.views_repository import ViewNotFoundError
from lib.views_repository import ViewPermissionError
from lib.views_repository import get_view_by_id
from utils.json_to_csv import export_csv_header
from utils.json_to_csv import export_host_to_csv_row

logger = get_logger(__name__)

HEADER_CONTENT_TYPE = {"json": "application/json; charset=utf-8", "csv": "text/csv; charset=utf-8"}


def _load_view_config(view_id: str, org_id: str, user_id: str) -> tuple[dict, dict, list[dict]]:
    """Load a saved view and extract its filters and columns.

    The view stores all filters under ``configuration.filters``, but ``query_filters()``
    accepts them in two different ways:
    - ``"host"`` filters (staleness, tags, dates …) → unpacked as **kwargs
    - everything else (system_profile, app-data) → passed as the ``filter=`` dict

    Returns:
        (host_filter, query_filter, columns):
        - host_filter: query_filters() kwargs (staleness, tags, date ranges, etc.)
        - query_filter: filter dict for query_filters() (system_profile, app-data, etc.)
        - columns: ordered list of column config dicts from the view
    """
    view = get_view_by_id(view_id, org_id, user_id)
    config_filters = view.configuration.get("filters") or {}
    columns = view.configuration.get("columns") or []

    host_filter: dict = {}
    query_filter: dict = {}

    for key, value in config_filters.items():
        if key == "host":
            for hk, hv in value.items():
                if hk in VALID_HOST_FILTER_KEYS:
                    host_filter[hk] = hv
        else:
            query_filter[key] = value

    # Views store "workspace_name" but query_filters() expects "group_name".
    workspace_name = host_filter.pop("workspace_name", None)
    if workspace_name:
        host_filter["group_name"] = [workspace_name] if isinstance(workspace_name, str) else workspace_name

    return host_filter, query_filter, columns


def resolve_export_columns(
    view_columns: list[dict],
) -> tuple[list[str], dict[str, list[str]]]:
    """Convert view column configs into an ordered export field list and app-data requirements.

    Returns:
        (export_fields, app_data_fields) where export_fields is the ordered list of flat
        field names for the export, and app_data_fields maps app_name -> [field_names]
        for app-data columns that need to be fetched separately.

    Note: Per-app RBAC is not applied here because the export consumer runs outside
    of a Flask request context. The export already requires host:view permission.
    """
    if not view_columns:
        # Legacy hosts-table export button: no View columns, keep the original
        # field set including static system-profile columns (os_release, etc.).
        return _EXPORT_SERVICE_FIELDS, {}

    all_models = get_app_data_models()

    export_fields: list[str] = list(ALWAYS_INCLUDED_EXPORT_FIELDS)
    app_data_fields: dict[str, list[str]] = {}

    for col in view_columns:
        key = col.get("key") or ""

        if key in CORE_VIEW_FIELDS_TO_EXPORT_FIELDS:
            for field in CORE_VIEW_FIELDS_TO_EXPORT_FIELDS[key]:
                if field not in export_fields:
                    export_fields.append(field)
        elif ":" in key:
            app_name, field_name = key.split(":", 1)
            model_class = all_models.get(app_name)
            if model_class and field_name in model_class._get_serializable_fields():
                fields_for_app = app_data_fields.setdefault(app_name, [])
                if field_name not in fields_for_app:
                    fields_for_app.append(field_name)
                flat_key = f"{app_name}:{field_name}"
                if flat_key not in export_fields:
                    export_fields.append(flat_key)

    return export_fields, app_data_fields


def _fetch_app_data_batch(
    host_ids: list,
    org_id: str,
    app_data_fields: dict[str, list[str]],
) -> dict[str, dict]:
    """Fetch app-data for a batch of hosts, returning {host_id_str: {app:field: value}}.

    Queries only the requested app tables (org_id equality + host_id IN (...)).
    This is used instead of LEFT JOINing every hosts_app_data_* table onto the
    hosts scan.
    """
    if not host_ids or not app_data_fields:
        return {}

    from app.models.database import db

    all_models = get_app_data_models()
    result: dict[str, dict] = {
        str(hid): {
            f"{app_name}:{field_name}": None for app_name, fnames in app_data_fields.items() for field_name in fnames
        }
        for hid in host_ids
    }

    for app_name, field_names in app_data_fields.items():
        model = all_models[app_name]
        rows = db.session.query(model).filter(model.org_id == org_id, model.host_id.in_(host_ids)).all()

        for row in rows:
            host_key = str(row.host_id)
            serialized = row.serialize()
            host_app = result.setdefault(host_key, {})
            for field_name in field_names:
                if field_name in serialized:
                    host_app[f"{app_name}:{field_name}"] = serialized[field_name]

    return result


class _StreamingExportBody:
    def __init__(self, host_iter: Iterator[dict], export_format: str, export_fields: list[str] | None = None):
        self._host_iter = host_iter
        self._export_format = export_format.lower()
        self._export_fields = export_fields or _EXPORT_SERVICE_FIELDS
        self._custom_fields = export_fields is not None
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
                if self._custom_fields:
                    yield json.dumps({field: host.get(field) for field in self._export_fields}).encode("utf-8")
                else:
                    yield json.dumps(host).encode("utf-8")
            yield b"]"
        elif self._export_format == "csv":
            yield export_csv_header(self._export_fields).encode("utf-8")
            for host in self._host_iter:
                self.host_count += 1
                yield export_host_to_csv_row(host, self._export_fields).encode("utf-8")
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
    try:
        token_response = oauth_client.get_token()
        return token_response.access_token
    except Exception:
        logger.exception("Failed to get export-service access token")
        raise


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
    identity: Identity,
    rbac_filter: dict | None,
    inventory_config: Config,
    query_filter: dict | None = None,
    host_filter: dict | None = None,
    export_fields: list[str] | None = None,
    app_data_fields: dict[str, list[str]] | None = None,
) -> Iterator[dict] | None:
    """Return a non-empty host iterator, or None if there are no hosts to export."""
    host_iter = get_hosts_to_export(
        identity,
        rbac_filter=rbac_filter,
        batch_size=inventory_config.export_svc_batch_size,
        query_filter=query_filter,
        host_filter=host_filter,
        export_fields=export_fields,
        app_data_fields=app_data_fields,
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

    export_service_endpoint = inventory_config.export_service_endpoint

    export_created = False
    session = Session()
    # Honor the per-endpoint CA certificate from the V2 dependency endpoint; fall back to system trust.
    session.verify = inventory_config.export_service_endpoint_ca_certificate or True

    try:
        rbac_request_headers, request_headers = build_headers(
            x_rh_identity, exportUUID, inventory_config, exportFormat
        )
    except Exception:
        logger.exception("Failed to build export-service request headers for export %s", exportUUID)
        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
        )
        error_headers = {"content-type": HEADER_CONTENT_TYPE[exportFormat.lower()]}
        if not inventory_config.export_service_endpoint_authenticated:
            error_headers["x-rh-exports-psk"] = inventory_config.export_service_token
        _handle_export_error(
            "Failed to authenticate with export-service",
            HTTPStatus.SERVICE_UNAVAILABLE,
            request_url,
            session,
            error_headers,
            exportUUID,
            exportFormat,
        )
        session.close()
        return export_created

    allowed, rbac_filter = resolve_permission(
        identity, KesselResourceTypes.HOST.view, rbac_request_headers=rbac_request_headers
    )

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

    export_filters = export_svc_data["data"]["resource_request"].get("filters") or {}
    view_id = export_filters.get("view_id")

    host_filter: dict = {}
    query_filter: dict = {}
    view_columns: list[dict] = []

    if view_id:
        user_id = identity.user_id
        if not user_id:
            request_url = _build_export_request_url(
                export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
            )
            _handle_export_error(
                "Export with view_id requires a User or ServiceAccount identity with a user_id.",
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
            host_filter, query_filter, view_columns = _load_view_config(view_id, identity.org_id, user_id)
            logger.info("Loaded view %s for export (org_id: %s)", view_id, identity.org_id)
        except ViewNotFoundError:
            request_url = _build_export_request_url(
                export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
            )
            _handle_export_error(
                f"View {view_id} not found or not accessible.",
                404,
                request_url,
                session,
                request_headers,
                exportUUID,
                exportFormat,
            )
            session.close()
            return export_created
        except ViewPermissionError as e:
            request_url = _build_export_request_url(
                export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
            )
            _handle_export_error(
                str(e.detail),
                403,
                request_url,
                session,
                request_headers,
                exportUUID,
                exportFormat,
            )
            session.close()
            return export_created

    export_fields, app_data_fields = resolve_export_columns(view_columns)

    try:
        hosts_iter = _non_empty_hosts_iter(
            identity,
            rbac_filter,
            inventory_config,
            query_filter=query_filter,
            host_filter=host_filter,
            export_fields=export_fields,
            app_data_fields=app_data_fields,
        )

        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "upload"
        )

        session.mount(request_url, HTTPAdapter(max_retries=3))

        logger.info(f"Trying to get data for org_id: {identity.org_id}")

        if hosts_iter is not None:
            logger.debug(f"Trying to upload data using URL:{request_url}")
            export_body = _StreamingExportBody(hosts_iter, exportFormat, export_fields=export_fields)
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


def _format_export_data(data: list[dict], exportFormat: str, export_fields: list[str] | None = None) -> str:
    """Materialize export payload for tests and small fixtures."""
    body = _StreamingExportBody(iter(data), exportFormat, export_fields=export_fields)
    return b"".join(body).decode("utf-8")
