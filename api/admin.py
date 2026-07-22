from http import HTTPStatus

from flask import Blueprint
from flask import jsonify
from flask import request

from app.common import inventory_config
from app.exceptions import InventoryException

admin_blueprint = Blueprint("admin", __name__)


@admin_blueprint.route("/_admin/hosts", methods=["POST"])
def create_or_update_admin_host():
    """Create or update a host for non-production data setup.

    Mounted at ``{api_url_path_prefix}/_admin/hosts`` (default
    ``/api/inventory/v1/_admin/hosts``). Not part of the public API spec.
    Gated by INVENTORY_ADMIN_HOSTS_ENABLED.
    """
    if not inventory_config().admin_hosts_endpoint_enabled:
        raise InventoryException(
            status=HTTPStatus.FORBIDDEN,
            title="Forbidden",
            detail="Admin hosts endpoint is disabled",
        )

    # Lazy imports avoid circular imports during app initialization.
    from lib.admin_hosts import create_or_update_host_via_admin
    from lib.host_repository import AddHostResult

    host_id, add_result = create_or_update_host_via_admin(request.get_json(silent=True))
    status = HTTPStatus.CREATED if add_result == AddHostResult.created else HTTPStatus.OK
    return jsonify({"id": str(host_id)}), status
