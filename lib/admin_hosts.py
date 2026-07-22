"""Admin endpoint helpers for creating/updating hosts outside of Kafka ingress."""

from __future__ import annotations

import uuid
from functools import partial
from typing import Any
from uuid import UUID

from flask import current_app

from api.staleness_query import get_staleness_obj
from app.auth.identity import create_mock_identity_with_org_id
from app.auth.identity import to_auth_header
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.instrumentation import log_add_host_attempt
from app.instrumentation import log_add_update_host_succeeded
from app.logging import get_logger
from app.models import Host
from app.models import db
from app.queue.events import operation_results_to_event_type
from app.serialization import deserialize_host
from lib.db import no_expire_on_commit
from lib.host_repository import AddHostResult
from lib.host_repository import add_host
from lib.host_repository import update_existing_host
from utils.system_profile_log import extract_host_dict_sp_to_log

logger = get_logger(__name__)


def create_or_update_host_via_admin(host_data: dict[str, Any] | None) -> tuple[UUID, AddHostResult]:
    """Create or update a host using the same persistence and event path as MQ ingress.

    - No ``id`` in the payload uses ``add_host`` (create, or update via canonical-fact
      deduplication — same as MQ ingress).
    - An ``id`` updates that existing host by primary key (404 if missing).
    Identity is derived from the host ``org_id`` (no request identity header required).
    """
    # Lazy imports avoid a circular import through app.queue.host_mq during app init.
    from app.queue.host_mq import OperationResult
    from app.queue.host_mq import write_add_update_event_message

    if not isinstance(host_data, dict):
        raise ValidationException("Request body must be valid JSON")

    org_id = host_data.get("org_id")
    if not org_id:
        raise ValidationException("org_id must be provided")

    host_id: UUID | None = None
    raw_host_id = host_data.get("id")
    if raw_host_id is not None:
        try:
            host_id = UUID(str(raw_host_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationException(f"Invalid host id: {raw_host_id}") from exc

    identity = create_mock_identity_with_org_id(org_id)
    if account := host_data.get("account"):
        identity.account_number = account

    input_host = deserialize_host(host_data)
    sp_fields_to_log = extract_host_dict_sp_to_log(host_data)
    log_add_host_attempt(logger, input_host, sp_fields_to_log, identity)

    if host_id is not None:
        existing_host = Host.query.filter(Host.id == host_id, Host.org_id == org_id).one_or_none()
        if existing_host is None:
            raise InventoryException(
                status=404,
                title="Not Found",
                detail=f"Host with id {host_id} was not found",
            )
        host_row, add_result = update_existing_host(existing_host, input_host, update_system_profile=True)
    else:
        # Match MQ ingress: assign an id, then add_host handles CF dedup + group wiring.
        input_host.id = uuid.uuid4()
        host_row, add_result = add_host(input_host, identity)

    success_logger = partial(log_add_update_host_succeeded, logger, add_result, sp_fields_to_log)
    result = OperationResult(
        host_row,
        {"b64_identity": to_auth_header(identity)},
        get_staleness_obj(identity.org_id),
        operation_results_to_event_type(add_result),
        success_logger,
    )

    with no_expire_on_commit(db.session):
        db.session.commit()
        write_add_update_event_message(
            current_app.event_producer,
            current_app.notification_event_producer,
            result,
        )

    return host_row.id, add_result
