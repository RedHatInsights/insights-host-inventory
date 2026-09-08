SUBMAN_CACHE_KEY_DELIMITER = "_subman="
SUBMAN_CACHE_INDEX_SUFFIX = "keys"


def system_cache_key_base(insights_id, org_id, owner_id):
    return f"insights_id={insights_id}_org={org_id}_user=SYSTEM-{owner_id}"


def subman_cache_index_key(base_key: str) -> str:
    return f"{base_key}{SUBMAN_CACHE_KEY_DELIMITER}{SUBMAN_CACHE_INDEX_SUFFIX}"


def subman_cache_key(base_key: str, forwarded_identity: str) -> str:
    return f"{base_key}{SUBMAN_CACHE_KEY_DELIMITER}{forwarded_identity}"
