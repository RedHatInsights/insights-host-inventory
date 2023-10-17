import connexion
import segment.analytics as analytics

from app.auth import get_current_identity


def segmentio_track(op_name, processing_time, contextual_data, logger):
    if analytics.write_key:
        user_agent_header = connexion.request.headers.get("User-Agent", "")
        if not user_agent_header:
            logger.debug("Skipping analytics.track(), User-Agent header not set")
            return None

        identity = get_current_identity()

        logger.debug(f"Calling analytics.track({identity.org_id}, {op_name}, ...)")
        analytics.track(
            identity.org_id,
            op_name,
            properties={
                "processing_time": processing_time,
                "status_code": contextual_data["status_code"],
                "user_agent": user_agent_header,
                "auth_type": identity.auth_type,
            },
            context={
                "app": {
                    "name": "Insights Host Inventory API",
                }
            },
        )
