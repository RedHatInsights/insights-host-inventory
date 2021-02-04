import base64
import json
import sys

"""
  Script to generate base64-encoded json and avoid forgetting or not
  thinking about new-line character, which is add by default when using
  "echo "asdfadsaf | base64".  The output to use is the generated in
  b'<generted_string>'.
"""
VALID_AUTH_TYPES = ["basic", "cert", "classic"]


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
        data = {
            "identity": {
                "account_number": "user_id_number",
                "type": "User",
                "auth_type": "basic-auth",
                "user": {"email": "tuser@redhat.com", "first_name": "test"},
            }
        }
    elif auth_type == "cert":
        data = {
            "identity": {
                "account_number": "sys_id_number",
                "type": "System",
                "auth_type": "cert-auth",
                "system": {"cn": "1b36b20f-7fa0-4454-a6d2-008294e06378", "cert_type": "system"},
                "internal": {"org_id": "3340851", "auth_time": 6300},
            }
        }

    else:  # auth type is classic
        data = {
            "account_number": "test",
            "auth_type": "classic-proxy",
            "internal": {"auth_time": 6300, "org_id": "3340851"},
            "system": {},
            "type": "System",
        }

    # turns json dict into s string
    data_dict = json.dumps(data)

    # base64.b64encode() needs bytes-like object NOT a string.
    apiKey = base64.b64encode(data_dict.encode("utf-8"))

    print("")
    print(f"For auth_type: {auth_type}: the encoded apiKey is:")
    print("")
    print(f"{apiKey}")
    print("")
    print(json.dumps(data, indent=2))
    print("")


# end of the main

if __name__ == "__main__":
    main(sys.argv)
    print("Done!!!\n")
