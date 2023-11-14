import connexion
import segment.analytics as analytics
import re

from app.auth import get_current_identity

USER_AGENT_IDENTIFIER = re.compile('Mozilla|Satellite|OpenAPI-Generator|insights-client')

def segmentio_track(op_name, processing_time, contextual_data, logger):
    if analytics.write_key:
        user_agent_header = connexion.request.headers.get("User-Agent", "")

        # Do not send track event for API requests from web browser, CLI, QE tests
        # or requests with missing User-Agent header
        if not user_agent_header or bool(re.search(USER_AGENT_IDENTIFIER, user_agent_header)):
            logger.debug("Skipping analytics.track(), request came from web browser, CLI or \
                QE test or User-Agent header was not set")
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
