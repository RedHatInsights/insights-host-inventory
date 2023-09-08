import connexion
import segment.analytics as analytics

from app.auth import get_current_identity


def segmentio_track(op_name, start_time, end_time, contextual_data):
    identity = get_current_identity()

    print(f"\n**** analytics.write_key: {analytics.write_key}")
    if analytics.write_key:
        print(f"**** Calling analytics.track({identity.org_id}, {op_name}, ...)")
        analytics.track(
            identity.org_id,
            op_name,
            properties={
                "start_time": start_time,
                "end_time": end_time,
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
    else:
        #
        # The following instrumentation will be replaced by the above track() call.
        # Its intent is to show the information available to track.
        #
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

    return True
