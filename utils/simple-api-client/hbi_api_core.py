import base64
import os

import requests

HBI_HOST = os.getenv("HBI_HOST", "http://0.0.0.0:8080")
API_PATH = os.getenv("API_PATH", "api/inventory/v1")

ORG_ID = os.getenv("ORG_ID", "0123456789")
# This value must match the system_profile_facts->owner_id value.
CN = os.getenv("CN", "1b36b20f-7fa0-4454-a6d2-008294e06378")


def gen_identity(identity):
    return base64.b64encode(identity.encode())


USER_IDENTITY_JSON = f"""{{
    "identity": {{
        "org_id":"{ORG_ID}",
        "type":"User",
        "auth_type":"BASIC-AUTH",
        "user":{{
            "username":"tuser@redhat.com",
            "email":"tuser@redhat.com",
            "first_name":"test",
            "last_name":"user",
            "is_active":true,
            "is_org_admin":false,
            "is_internal":true,
            "locale":"en_US"
        }}
    }}
}}"""
USER_IDENTITY_ENC = gen_identity(USER_IDENTITY_JSON)

SYSTEM_IDENTITY_JSON = f"""{{
    "identity":{{
        "org_id": "{ORG_ID}",
        "auth_type": "cert-auth",
        "internal": {{"org_id": "{ORG_ID}"}},
        "system": {{
            "cert_type": "system",
            "cn": "{CN}"
        }}
        "type": "System"
    }}
}}"""
SYSTEM_IDENTITY_ENC = gen_identity(SYSTEM_IDENTITY_JSON)


def process_response(response):
    response.raise_for_status()
    print(response.json())


def hbi_get(endpoint, additional_headers={}, params={}, identity=USER_IDENTITY_ENC):
    headers = {"x-rh-identity": identity} | additional_headers
    response = requests.get(f"{HBI_HOST}/{API_PATH}/{endpoint}", headers=headers, params=params)
    return response
