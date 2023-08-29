# import segment.analytics as analytics
import connexion

from app.auth import get_current_identity

# TBD - including location of this initialization
#
# analytics.write_key = 'YOUR_WRITE_KEY'


def segmentio_track(op_name, start_time, end_time, contextual_data):
    identity = get_current_identity()

    # analytics.track(
    #     identity.org_id,
    #     op_name,
    #     {
    #         start_time: start_time,
    #         end_time: end_time
    #         user_agent: connexion.request.headers['User-Agent']
    #     }
    # )

    print(f"\n************ In api_operation: {op_name}")
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
