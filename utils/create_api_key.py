import base64
import json
import sys

"""
  This script is used to generate a base64-encoded apiKey using the same json input for a
  desired identity.  There have been occasions when a considerable amount of time was spent
  to determine why the hosts in DB were not accessible using REST API.  The reason turned
  out was using a different apikey for accessing hosts than the one used for creating hosts.

  To generate an apiKey, run:
  "python create_api_key.py basic"

  To see what `auth_type` options are available, run:
  "python create_api_key"
"""
VALID_AUTH_TYPES = ["basic", "cert", "classic"]

SYSTEM_IDENTITY = {
    "identity": {
        "account_number": "sysaccount",
        "type": "System",
        "auth_type": "cert-auth",
        "system": {"cn": "1b36b20f-7fa0-4454-a6d2-008294e06378", "cert_type": "system"},
        "internal": {"org_id": "3340851", "auth_time": 6300},
    }
}

USER_IDENTITY = {
    "identity": {
        "account_number": "usraccount",
        "type": "User",
        "auth_type": "basic-auth",
        "user": {"email": "tuser@redhat.com", "first_name": "test"},
    }
}

INSIGHTS_CLASSIC_IDENTITY = {
    "identity": {
        "account_number": "classic",
        "auth_type": "classic-proxy",
        "internal": {"auth_time": 6300, "org_id": "3340851"},
        "system": {},
        "type": "System",
    }
}


def main(argv):
    if len(argv) < 2:
        print("Provide a valid authentication type")
        print("A valid command is python create_api_key.py basic, cert, or classic")
        exit(1)

    auth_type = argv[1]
    if auth_type not in VALID_AUTH_TYPES:
        print("Provide a valid authentication type")
        print('A valid command is "python create_api_key.py basic, cert, or classic"')
        exit(2)

    if auth_type == "basic":
        data = USER_IDENTITY
    elif auth_type == "cert":
        data = SYSTEM_IDENTITY
    else:  # auth type is classic
        data = INSIGHTS_CLASSIC_IDENTITY

    # turns json dict into s string
    data_dict = json.dumps(data)

    # base64.b64encode() needs bytes-like object NOT a string.
    apiKey = base64.b64encode(data_dict.encode("utf-8"))

    print(f"\nFor auth_type: {auth_type}: the encoded apiKey is:\n")
    print(f"{apiKey}\n")
    print(json.dumps(data, indent=2))


# end of the main

if __name__ == "__main__":
    main(sys.argv)
    print("\nDone!!!\n")
