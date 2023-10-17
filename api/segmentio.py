import connexion
import segment.analytics as analytics

from app.auth import get_current_identity


def segmentio_track(op_name, processing_time, contextual_data, logger):
    identity = get_current_identity()

    if analytics.write_key:
        logger.debug(f"Calling analytics.track({identity.org_id}, {op_name}, ...)")
        analytics.track(
            identity.org_id,
            op_name,
            properties={
                "processing_time": processing_time,
                "status_code": contextual_data["status_code"],
                "user_agent": connexion.request.headers["User-Agent"],
                "auth_type": identity.auth_type,
            },
            context={
                "app": {
                    "name": "Insights Host Inventory API",
                }
            },
        )
