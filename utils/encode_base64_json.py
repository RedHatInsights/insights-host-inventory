import base64
import json

"""
  Script to generate base64-encoded json and avoid forgetting or not
  thinking about new-line character, which is add by default when using
  "echo "asdfadsaf | base64".  The output to use is the generated in
  b'<generted_string>'.
"""

data = {
    "identity": {
        "account_number": "test",
        "type": "System",
        "auth_type": "cert-auth",
        "system": {"cn": "1b36b20f-7fa0-4454-a6d2-008294e06378", "cert_type": "system"},
        "internal": {"org_id": "3340851", "auth_time": 6300},
    }
}

# turns json dict into s string
data_dict = json.dumps(data)

# base64.b64encode() needs bytes-like object NOT a string.
apiKey = base64.b64encode(data_dict.encode("utf-8"))

print("")
print("The encoded apiKey is:")
print(f"{apiKey}")
print("")
print("")
print("Done!!!")
