"""Redis Lua scripts for atomic system-cache invalidation and registration."""

from api.system_cache_key import SUBMAN_CACHE_KEY_DELIMITER
from api.system_cache_key import subman_cache_index_key

CACHE_PREFIX = "flask_cache_"
INVALIDATION_LOCK_SUFFIX = ":invalidating"
INDEX_DELETING_SUFFIX = ":deleting"

# Atomically invalidate a system cache entry:
# 1. Set a short-lived lock so concurrent registrations are skipped.
# 2. RENAME the index set so in-flight SMEMBERS/delete cannot race with SADD.
# 3. Delete indexed forwarded-identity keys.
# 4. SCAN for legacy unindexed forwarded-identity keys (pre-index deployments).
# 5. Delete any index recreated during invalidation and its members.
# KEYS[1] = prefixed index key
# KEYS[2] = prefixed base cache key
# KEYS[3] = prefixed invalidation lock key
# ARGV[1] = legacy SCAN match pattern
# ARGV[2] = prefixed subman key prefix for indexed members
INVALIDATE_SYSTEM_CACHE_KEYS_LUA = """
local index_key = KEYS[1]
local base_key = KEYS[2]
local lock_key = KEYS[3]
local scan_pattern = ARGV[1]
local subman_prefix = ARGV[2]

redis.call('SET', lock_key, '1', 'EX', 30)

local keys_to_delete = {}
local seen = {}
local deleted_count = 0

local function add_key(key)
  if not seen[key] then
    seen[key] = true
    keys_to_delete[#keys_to_delete + 1] = key
  end
end

add_key(base_key)

if redis.call('EXISTS', index_key) == 1 then
  local temp_index = index_key .. ':deleting'
  redis.call('RENAME', index_key, temp_index)
  for _, member in ipairs(redis.call('SMEMBERS', temp_index)) do
    add_key(subman_prefix .. member)
  end
  add_key(temp_index)
end

local cursor = '0'
repeat
  local result = redis.call('SCAN', cursor, 'MATCH', scan_pattern, 'COUNT', 100)
  cursor = result[1]
  for _, key in ipairs(result[2]) do
    add_key(key)
  end
until cursor == '0'

if redis.call('EXISTS', index_key) == 1 then
  for _, member in ipairs(redis.call('SMEMBERS', index_key)) do
    add_key(subman_prefix .. member)
  end
  add_key(index_key)
end

redis.call('DEL', lock_key)

if #keys_to_delete > 0 then
  deleted_count = redis.call('UNLINK', unpack(keys_to_delete))
end

return deleted_count
"""

# Register a forwarded-identity cache key in the index unless invalidation is active.
# KEYS[1] = prefixed index key
# KEYS[2] = prefixed invalidation lock key
# ARGV[1] = forwarded identity UUID
# ARGV[2] = index TTL seconds
REGISTER_SUBMAN_CACHE_KEY_LUA = """
local index_key = KEYS[1]
local lock_key = KEYS[2]
local member = ARGV[1]
local ttl = tonumber(ARGV[2])

if redis.call('EXISTS', lock_key) == 1 then
  return 0
end

redis.call('SADD', index_key, member)
redis.call('EXPIRE', index_key, ttl)
return 1
"""


def prefixed_base_cache_key(base_key: str) -> str:
    return f"{CACHE_PREFIX}{base_key}"


def prefixed_subman_cache_key(base_key: str, forwarded_identity: str) -> str:
    return f"{CACHE_PREFIX}{base_key}{SUBMAN_CACHE_KEY_DELIMITER}{forwarded_identity}"


def prefixed_subman_index_key(base_key: str) -> str:
    return f"{CACHE_PREFIX}{subman_cache_index_key(base_key)}"


def prefixed_subman_key_prefix(base_key: str) -> str:
    return f"{CACHE_PREFIX}{base_key}{SUBMAN_CACHE_KEY_DELIMITER}"


def prefixed_invalidation_lock_key(base_key: str) -> str:
    return f"{prefixed_subman_index_key(base_key)}{INVALIDATION_LOCK_SUFFIX}"


def legacy_subman_scan_pattern(base_key: str) -> str:
    return f"{prefixed_subman_key_prefix(base_key)}*"
