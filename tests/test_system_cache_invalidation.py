from api.system_cache_invalidation import legacy_subman_scan_pattern
from api.system_cache_invalidation import prefixed_cache_generation_key
from api.system_cache_invalidation import prefixed_subman_index_key
from api.system_cache_invalidation import prefixed_subman_key_prefix
from api.system_cache_key import subman_cache_key
from api.system_cache_key import system_cache_key_base
from tests.helpers.test_utils import generate_uuid


def test_legacy_subman_scan_pattern_matches_forwarded_identity_keys():
    base_key = system_cache_key_base(generate_uuid(), "test", "owner")
    forwarded_identity = generate_uuid()

    pattern = legacy_subman_scan_pattern(base_key)
    assert pattern == f"{prefixed_subman_key_prefix(base_key)}*"
    assert pattern.startswith(prefixed_subman_key_prefix(base_key))
    assert subman_cache_key(base_key, forwarded_identity).endswith(forwarded_identity)


def test_prefixed_cache_generation_key_uses_index_key():
    base_key = system_cache_key_base(generate_uuid(), "test", "owner")
    assert prefixed_cache_generation_key(base_key) == f"{prefixed_subman_index_key(base_key)}:generation"
