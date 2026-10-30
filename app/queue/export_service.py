from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from http import HTTPStatus
from typing import Any
from uuid import UUID

from requests import Response
from requests import Session
from requests.adapters import HTTPAdapter

from api.filtering.app_data_sorting import get_app_name_from_sort
from api.host_query_db import get_hosts_to_export
from api.views_validation import VALID_HOST_FILTER_KEYS
from api.views_validation import validate_view_configuration
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app.auth.identity import Identity
from app.auth.identity import from_auth_header
from app.auth.rbac import KesselResourceTypes
from app.config import Config
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.logging import threadctx
from app.models.host_app_data import get_app_data_models
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import ALWAYS_INCLUDED_EXPORT_FIELDS
from app.serialization import CORE_VIEW_FIELDS_TO_EXPORT_FIELDS
from lib import metrics
from lib.kessel import get_kessel_oauth2_credentials
from lib.middleware import get_allowed_app_services
from lib.middleware import resolve_permission
from lib.views_repository import ViewNotFoundError
from lib.views_repository import ViewPermissionError
from lib.views_repository import get_view_by_id
from utils.json_to_csv import export_csv_header
from utils.json_to_csv import export_host_to_csv_row

logger = get_logger(__name__)

HEADER_CONTENT_TYPE = {"json": "application/json; charset=utf-8", "csv": "text/csv; charset=utf-8"}

_DEDICATED_HOST_FILTER_APPS = {
    "advisor": ("recommendation_severity", "incident_status"),
    "vulnerability": ("cve_severity", "known_exploit", "security_rule"),
}


def _check_dedicated_host_filter_permissions(
    allowed_apps: set[str] | None,
    host_filter: dict,
) -> str | None:
    """Return the name of the first app whose dedicated host filters are used without permission, or None."""
    if allowed_apps is None:
        return None
    for app_name, filter_keys in _DEDICATED_HOST_FILTER_APPS.items():
        if app_name not in allowed_apps and any(host_filter.get(k) for k in filter_keys):
            return app_name
    return None


def _config_filters_to_query_filters(config_filters: dict) -> tuple[dict, dict]:
    """Split a view configuration's ``filters`` into query_filters() inputs.

    Host-level filters (the ``"host"`` namespace: staleness, tags, dates …) are
    kept as ``HostFilters`` fields, while system-profile and app-data filters
    remain in the ``query_filter`` dict.

    Returns:
        (host_filter, query_filter):
        - host_filter: HostFilters fields (staleness, tags, date ranges, etc.)
        - query_filter: system-profile and app-data filter dictionary
    """
    host_filter: dict = {}
    query_filter: dict = {}

    for key, value in config_filters.items():
        if key == "host":
            for hk, hv in value.items():
                if hk in VALID_HOST_FILTER_KEYS:
                    host_filter[hk] = hv
        else:
            query_filter[key] = value

    # Configurations store "workspace_name" but query_filters() expects "group_name".
    workspace_name = host_filter.pop("workspace_name", None)
    if workspace_name:
        host_filter["group_name"] = [workspace_name] if isinstance(workspace_name, str) else workspace_name

    return host_filter, query_filter


def _config_to_export_inputs(configuration: dict) -> tuple[dict, dict, list[dict], str | None, str | None]:
    """Derive export query inputs from a view configuration dict.

    Shared by the saved-view (``view_id``) path and the inline-configuration path so
    both produce identical filters, columns, and sort.

    Returns:
        (host_filter, query_filter, columns, order_by, order_how)
    """
    config_filters = configuration.get("filters") or {}
    columns = configuration.get("columns") or []

    host_filter, query_filter = _config_filters_to_query_filters(config_filters)

    sort = configuration.get("sort") or {}
    order_by = sort.get("key") or None
    direction = sort.get("direction")
    order_how = direction.upper() if isinstance(direction, str) else None

    return host_filter, query_filter, columns, order_by, order_how


def _load_view_config(
    view_id: str, org_id: str, user_id: str
) -> tuple[dict, dict, list[dict], str | None, str | None]:
    """Load a saved view and extract its filters, columns, and sort.

    Returns:
        (host_filter, query_filter, columns, order_by, order_how)
    """
    view = get_view_by_id(view_id, org_id, user_id)
    return _config_to_export_inputs(view.configuration)


# Composite UI columns render several underlying app-data fields as a single
# table cell (e.g. the "Vulnerabilities" column shows one severity count per
# icon).  They only exist in the frontend, so exports replace them with their
# individual app-data fields to ship the raw counts instead of the combined
# display value.
COMPOSITE_VIEW_FIELDS_TO_EXPORT_FIELDS: dict[str, list[str]] = {
    "advisor:recommendations": [
        "advisor:critical",
        "advisor:important",
        "advisor:moderate",
        "advisor:low",
    ],
    "vulnerability:total_cves": [
        "vulnerability:critical_cves",
        "vulnerability:important_cves",
        "vulnerability:moderate_cves",
        "vulnerability:low_cves",
    ],
    "patch:advisories_rhsa_installable": [
        "patch:advisories_rhsa_installable",
        "patch:advisories_rhba_installable",
        "patch:advisories_rhea_installable",
        "patch:advisories_other_installable",
    ],
}

# Fields a view column can select for the export.
_SELECTABLE_EXPORT_FIELDS = frozenset(
    field for fields in CORE_VIEW_FIELDS_TO_EXPORT_FIELDS.values() for field in fields
)

# The fields every view-configuration export appends after the selected
# columns: the legacy export fields that no manage-columns entry can produce
# (customers asked for this data in exports beyond what the table displays),
# plus "updated", which stays present even when deselected so the legacy
# export's guarantee holds. Derived from _EXPORT_SERVICE_FIELDS and
# CORE_VIEW_FIELDS_TO_EXPORT_FIELDS (app/serialization.py) so it cannot drift
# from them; "host_id" is always included up front instead of appended.
ALWAYS_APPENDED_EXPORT_FIELDS = [
    field
    for field in _EXPORT_SERVICE_FIELDS
    if field != "host_id" and (field == "updated" or field not in _SELECTABLE_EXPORT_FIELDS)
]


def _expand_view_columns(view_columns: list[dict]) -> list[dict]:
    """Expand composite UI columns into their individual app-data columns.

    Each expanded column flows through the same app-authorization, field
    validation, and deduplication rules as a directly selected column.
    """
    expanded: list[dict] = []
    for col in view_columns:
        key = col.get("key") or ""
        if key in COMPOSITE_VIEW_FIELDS_TO_EXPORT_FIELDS:
            expanded.extend({"key": field} for field in COMPOSITE_VIEW_FIELDS_TO_EXPORT_FIELDS[key])
        else:
            expanded.append(col)
    return expanded


def resolve_export_columns(
    view_columns: list[dict],
    allowed_apps: set[str] | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
    """Convert view column configs into an ordered export field list and app-data requirements.

    Args:
        view_columns: Ordered list of column configurations from the view.
            Composite UI columns (e.g. ``vulnerability:total_cves``) are
            expanded into their individual app-data fields.
        allowed_apps: Optional set of permitted app names. When provided, columns
            belonging to unauthorized applications are omitted from the export.

    Returns:
        (export_fields, app_data_fields) where export_fields is the ordered list of flat
        field names for the export, and app_data_fields maps app_name -> [field_names]
        for app-data columns that need to be fetched separately.
    """
    if not view_columns:
        # Legacy hosts-table export button: no View columns, keep the original
        # field set including static system-profile columns (os_release, etc.).
        return _EXPORT_SERVICE_FIELDS, {}

    all_models = get_app_data_models()

    export_fields: list[str] = list(ALWAYS_INCLUDED_EXPORT_FIELDS)
    app_data_fields: dict[str, list[str]] = {}

    for col in _expand_view_columns(view_columns):
        key = col.get("key") or ""

        if key in CORE_VIEW_FIELDS_TO_EXPORT_FIELDS:
            for field in CORE_VIEW_FIELDS_TO_EXPORT_FIELDS[key]:
                if field not in export_fields:
                    export_fields.append(field)
        elif ":" in key:
            app_name, field_name = key.split(":", 1)
            if allowed_apps is not None and app_name not in allowed_apps:
                continue
            model_class = all_models.get(app_name)
            if model_class and field_name in model_class._get_serializable_fields():
                fields_for_app = app_data_fields.setdefault(app_name, [])
                if field_name not in fields_for_app:
                    fields_for_app.append(field_name)
                flat_key = f"{app_name}:{field_name}"
                if flat_key not in export_fields:
                    export_fields.append(flat_key)

    # Fields no manage-columns entry can select are always appended after the
    # selected columns (see ALWAYS_APPENDED_EXPORT_FIELDS).
    for field in ALWAYS_APPENDED_EXPORT_FIELDS:
        if field not in export_fields:
            export_fields.append(field)

    return export_fields, app_data_fields


def _format_compliance_policies(policies: Any) -> str | None:
    """Extract policy names from compliance policies JSON array for export."""
    if not policies:
        return None
    if isinstance(policies, list):
        names = []
        for p in policies:
            if isinstance(p, dict):
                name = p.get("name") or p.get("id")
                if name:
                    names.append(str(name))
            elif isinstance(p, str):
                names.append(p)
        return ", ".join(names) if names else None
    if isinstance(policies, str):
        return policies
    return None


def _fetch_app_data_batch(
    host_ids: list,
    org_id: str,
    app_data_fields: dict[str, list[str]],
) -> dict[str, dict]:
    """Fetch app-data for a batch of hosts, returning {host_id_str: {app:field: value}}.

    Queries only the requested app tables (org_id equality + host_id IN (...)).
    This is used instead of LEFT JOINing every hosts_app_data_* table onto the
    hosts scan.

    Uses a separate Session so these lookups can run while ``get_hosts_to_export``
    still holds a ``yield_per`` server-side cursor on ``db.session``.
    """
    if not host_ids or not app_data_fields:
        return {}

    from sqlalchemy.orm import Session as OrmSession

    from app.models.database import db

    all_models = get_app_data_models()
    result: dict[str, dict] = {
        str(hid): {
            f"{app_name}:{field_name}": None for app_name, fnames in app_data_fields.items() for field_name in fnames
        }
        for hid in host_ids
    }

    with OrmSession(bind=db.engine) as app_session:
        for app_name, field_names in app_data_fields.items():
            model = all_models[app_name]
            rows = app_session.query(model).filter(model.org_id == org_id, model.host_id.in_(host_ids)).all()

            for row in rows:
                host_key = str(row.host_id)
                serialized = row.serialize()
                host_app = result.setdefault(host_key, {})
                for field_name in field_names:
                    if field_name in serialized:
                        val = serialized[field_name]
                        if app_name == "compliance" and field_name == "policies":
                            val = _format_compliance_policies(val)
                        host_app[f"{app_name}:{field_name}"] = val

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


def extract_export_svc_data(export_svc_data: dict) -> tuple[str, UUID, str, str, str, str | None, dict | None]:
    """Extract the export-service request fields and the inventory view filters.

    The ``filters`` field carries the inventory-specific export options: either a
    saved ``view_id`` or an inline ``configuration`` mirroring the ViewConfiguration
    schema from swagger/api.spec.yaml (the same shape the saved-views API accepts).
    """
    resource_request = export_svc_data["data"]["resource_request"]
    exportFormat = resource_request["format"]
    exportUUID = resource_request["export_request_uuid"]
    applicationName = resource_request["application"]
    resourceUUID = resource_request["uuid"]
    identityHeader = resource_request["x_rh_identity"]

    export_filters = resource_request.get("filters") or {}
    view_id = export_filters.get("view_id")
    # Inline configuration carries the table's live (possibly unsaved) filters,
    # columns, and sort for a WYSIWYG export.
    configuration = export_filters.get("configuration")

    return exportFormat, exportUUID, applicationName, resourceUUID, identityHeader, view_id, configuration


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
    order_by: str | None = None,
    order_how: str | None = None,
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
        order_by=order_by,
        order_how=order_how,
    )
    first_host = next(host_iter, None)
    if first_host is None:
        return None
    return itertools.chain([first_host], host_iter)


@metrics.create_export_processing_time.time()
def create_export(
    export_svc_data: dict,
    inventory_config: Config,
    operation_args: dict | None = None,
    rbac_filter: dict | None = None,
) -> bool:
    if operation_args is None:
        operation_args = {}
    if rbac_filter is None:
        rbac_filter = {}

    (
        exportFormat,
        exportUUID,
        applicationName,
        resourceUUID,
        identityHeader,
        view_id,
        configuration,
    ) = extract_export_svc_data(export_svc_data)
    # Kafka path has no Flask before_request; this is the same ID we send as x-rh-insights-request-id.
    threadctx.request_id = str(exportUUID)

    identity = from_auth_header(identityHeader)

    metrics.create_export_count.inc()
    logger.info("Creating export for HBI")

    export_service_endpoint = inventory_config.export_service_endpoint

    export_created = False
    session = Session()
    # Honor the per-endpoint CA certificate from the V2 dependency endpoint; fall back to system trust.
    session.verify = inventory_config.export_service_endpoint_ca_certificate or True

    try:
        rbac_request_headers, request_headers = build_headers(
            identityHeader, exportUUID, inventory_config, exportFormat
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

    host_filter: dict = {}
    query_filter: dict = {}
    view_columns: list[dict] = []
    order_by: str | None = None
    order_how: str | None = None
    allowed_apps: set[str] | None = None

    def _fail(message: str, status_code: int) -> None:
        request_url = _build_export_request_url(
            export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
        )
        _handle_export_error(message, status_code, request_url, session, request_headers, exportUUID, exportFormat)
        session.close()

    if view_id:
        user_id = identity.user_id
        if not user_id:
            _fail("Export with view_id requires a User or ServiceAccount identity with a user_id.", 403)
            return export_created

        try:
            host_filter, query_filter, view_columns, order_by, order_how = _load_view_config(
                view_id, identity.org_id, user_id
            )
            logger.info("Loaded view %s for export (org_id: %s)", view_id, identity.org_id)
        except ViewNotFoundError:
            _fail(f"View {view_id} not found or not accessible.", 404)
            return export_created
        except ViewPermissionError as e:
            _fail(str(e.detail), 403)
            return export_created
    elif configuration is not None:
        if not isinstance(configuration, dict) or not configuration.get("columns"):
            # A supplied configuration must name the columns to export. Falling through
            # with no columns would silently export the broad legacy field set instead
            # of the requested (WYSIWYG) view.
            _fail("Invalid export configuration: 'columns' is required.", 400)
            return export_created
        try:
            validate_view_configuration(configuration)
        except ValidationException as e:
            _fail(f"Invalid export configuration: {e.detail}", 400)
            return export_created
        host_filter, query_filter, view_columns, order_by, order_how = _config_to_export_inputs(configuration)
        logger.info("Using inline export configuration (org_id: %s)", identity.org_id)

    if view_id or configuration is not None:
        allowed_apps = get_allowed_app_services(identity, rbac_request_headers=rbac_request_headers)
        if allowed_apps is not None:
            known_apps = set(get_app_data_models().keys())
            if query_filter:
                denied_filters = [k for k in query_filter if k in known_apps and k not in allowed_apps]
                if denied_filters:
                    _fail(f"Insufficient permissions to filter by {denied_filters}", 403)
                    return export_created
            sort_app = get_app_name_from_sort(order_by)
            if sort_app is not None and sort_app not in allowed_apps:
                _fail(f"Insufficient permissions to sort by '{order_by}'", 403)
                return export_created

        denied_app = _check_dedicated_host_filter_permissions(allowed_apps, host_filter)
        if denied_app:
            request_url = _build_export_request_url(
                export_service_endpoint, exportUUID, applicationName, resourceUUID, "error"
            )
            _handle_export_error(
                f"Insufficient permissions to filter by {denied_app}",
                403,
                request_url,
                session,
                request_headers,
                exportUUID,
                exportFormat,
            )
            session.close()
            return export_created

    export_fields, app_data_fields = resolve_export_columns(view_columns, allowed_apps=allowed_apps)

    try:
        hosts_iter = _non_empty_hosts_iter(
            identity,
            rbac_filter,
            inventory_config,
            query_filter=query_filter,
            host_filter=host_filter,
            export_fields=export_fields,
            app_data_fields=app_data_fields,
            order_by=order_by,
            order_how=order_how,
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
    return f"{export_service_endpoint}/internal/export/v1/{exportUUID}/{applicationName}/{resourceUUID}/{request_type}"


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
