# HBI supported identities

__all__ = ("get_system_cert_auth_identity", "get_system_classic_identity", "get_user_basic_auth_identity")


SYSTEM_IDENTITY = {
    "identity": {
        "account_number": "sysaccount",
        "auth_type": "cert-auth",
        "internal": {"auth_time": 6300, "org_id": "3340851"},
        "system": {"cert_type": "system", "cn": "1b36b20f-7fa0-4454-a6d2-008294e06378"},
        "type": "System",
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

USER_IDENTITY = {
    "identity": {
        "account_number": "usraccount",
        "type": "User",
        "auth_type": "basic-auth",
        "user": {"email": "tuser@redhat.com", "first_name": "test"},
    }
}


def get_system_cert_auth_identity():
    return SYSTEM_IDENTITY


def get_system_classic_identity():
    return INSIGHTS_CLASSIC_IDENTITY


def get_user_basic_auth_identity():
    return USER_IDENTITY
