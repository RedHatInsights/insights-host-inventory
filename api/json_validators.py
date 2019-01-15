import uuid

from jsonschema import draft4_format_checker


@draft4_format_checker.checks('uuid')
def verify_uuid_format(uuid_str):
    if uuid_str is None:
        # UUID fields are nullable
        return True

    try:
        uuid.UUID(uuid_str, version=4)
    except:
        return False
    return True
