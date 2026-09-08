SUBMAN_CACHE_KEY_DELIMITER = "_subman="


def system_cache_key_base(insights_id, org_id, owner_id):
    return f"insights_id={insights_id}_org={org_id}_user=SYSTEM-{owner_id}"
