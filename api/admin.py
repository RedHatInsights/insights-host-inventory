from http import HTTPStatus

from flask import Blueprint
from flask import jsonify
from flask import request

from app.common import inventory_config
from app.exceptions import ValidationException

admin_blueprint = Blueprint("admin", __name__)


@admin_blueprint.route("/_admin/hosts", methods=["POST"])
def create_or_update_admin_host():
    """Create or update a host for non-production data setup.

    Not part of the public API spec. Gated by INVENTORY_ADMIN_HOSTS_ENABLED.
    """
    if not inventory_config().admin_hosts_endpoint_enabled:
        return jsonify({"detail": "Admin hosts endpoint is disabled", "status": 403, "title": "Forbidden"}), 403

    host_data = request.get_json(silent=True)
    if host_data is None:
        raise ValidationException("Request body must be valid JSON")

    # Lazy imports avoid circular imports during app initialization.
    from lib.admin_hosts import create_or_update_host_via_admin
    from lib.host_repository import AddHostResult

    host_id, add_result = create_or_update_host_via_admin(host_data)
    status = HTTPStatus.CREATED if add_result == AddHostResult.created else HTTPStatus.OK
    return jsonify({"id": str(host_id)}), status
