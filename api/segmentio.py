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
    """
    else:
        print(f"************ In api_operation: {op_name}")
        print("  Headers:")
        for key, value in connexion.request.headers.items():
            print(f"    {key}: {value}")

        print()
        print("  Identity:")
        print(f"    identity_type: {identity.identity_type}")
        print(f"    auth_type: {identity.auth_type}")
        print(f"    is_trusted_system: {identity.is_trusted_system}")
        print(f"    org_id: {identity.org_id}")
        print(f"    account_number: {identity.account_number}")

        if identity.identity_type == "User":
            print(f"    User: {identity.user}")
        else:
            print(f"    System: {identity.system}")

        print()
        print("  contextual_data:")
        for key, value in contextual_data.items():
            print(f"    {key}: {value}")

        print("************\n")
    """

    return True
