Unable to configure watchtower logging.  Please verify watchtower logging configuration!
[2025-03-07 03:45:51,463] [2887625] [140501292804480] [inventory.app.config] [INFO] Insights Host Inventory Configuration:
[2025-03-07 03:45:51,463] [2887625] [140501292804480] [inventory.app.config] [INFO] Insights Host Inventory Configuration:
[2025-03-07 03:45:51,463] [2887625] [140501292804480] [inventory.app.config] [INFO] Build Version: Unknown
[2025-03-07 03:45:51,463] [2887625] [140501292804480] [inventory.app.config] [INFO] Build Version: Unknown
[2025-03-07 03:45:51,464] [2887625] [140501292804480] [inventory.app.config] [INFO] DB Host: localhost
[2025-03-07 03:45:51,464] [2887625] [140501292804480] [inventory.app.config] [INFO] DB Host: localhost
[2025-03-07 03:45:51,464] [2887625] [140501292804480] [inventory.app.config] [INFO] DB Name: insights
[2025-03-07 03:45:51,464] [2887625] [140501292804480] [inventory.app.config] [INFO] DB Name: insights
[2025-03-07 03:45:51,464] [2887625] [140501292804480] [inventory.app.config] [INFO] DB Connection URI: postgresql://xxxx:XXXX@localhost:5432/insights
[2025-03-07 03:45:51,464] [2887625] [140501292804480] [inventory.app.config] [INFO] DB Connection URI: postgresql://xxxx:XXXX@localhost:5432/insights
[2025-03-07 03:45:53,030] [2887625] [140501292804480] [inventory.app] [INFO] Listening on API: /api/inventory/v1
[2025-03-07 03:45:53,030] [2887625] [140501292804480] [inventory.app] [INFO] Listening on API: /api/inventory/v1
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.app] [INFO] Listening on API: /r/insights/platform/inventory/v1
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.app] [INFO] Listening on API: /r/insights/platform/inventory/v1
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.cache] [INFO] Initializing Cache
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.cache] [INFO] Initializing Cache
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.cache] [INFO] Cache using config={'CACHE_TYPE': 'NullCache', 'CACHE_DEFAULT_TIMEOUT': 0}
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.cache] [INFO] Cache using config={'CACHE_TYPE': 'NullCache', 'CACHE_DEFAULT_TIMEOUT': 0}
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.cache] [INFO] Cache initialized with app.
[2025-03-07 03:45:53,166] [2887625] [140501292804480] [inventory.cache] [INFO] Cache initialized with app.
[2025-03-07 03:45:53,168] [2887625] [140501292804480] [inventory.app] [WARNING] Unleash is bypassed by config value. Feature flag toggles will default to their fallback values.
[2025-03-07 03:45:53,168] [2887625] [140501292804480] [inventory.app] [WARNING] Unleash is bypassed by config value. Feature flag toggles will default to their fallback values.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app] [WARNING] WARNING: The event producer has been disabled.  The message queue based event notifications have been disabled.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app] [WARNING] WARNING: The event producer has been disabled.  The message queue based event notifications have been disabled.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app] [WARNING] WARNING: The event producer has been disabled.  The message queue based notifications have been disabled.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app] [WARNING] WARNING: The event producer has been disabled.  The message queue based notifications have been disabled.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app] [WARNING] WARNING: Using the NullProducer for the payload tracker producer.  No payload tracker events will be sent to to payload tracker.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app] [WARNING] WARNING: Using the NullProducer for the payload tracker producer.  No payload tracker events will be sent to to payload tracker.
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app.payload_tracker] [INFO] Using injected producer object (<app.payload_tracker.NullProducer object at 0x7fc8eebee0d0>) for PayloadTracker
[2025-03-07 03:45:53,207] [2887625] [140501292804480] [inventory.app.payload_tracker] [INFO] Using injected producer object (<app.payload_tracker.NullProducer object at 0x7fc8eebee0d0>) for PayloadTracker
[2025-03-07 03:45:53,208] [2887625] [140501292804480] [inventory.app] [INFO] Initializing Segmentio
[2025-03-07 03:45:53,208] [2887625] [140501292804480] [inventory.app] [INFO] Initializing Segmentio
[2025-03-07 03:45:53,208] [2887625] [140501292804480] [inventory.app] [INFO] Registering Segmentio flush on shutdown
[2025-03-07 03:45:53,208] [2887625] [140501292804480] [inventory.app] [INFO] Registering Segmentio flush on shutdown
[2025-03-07 03:45:53,212] [2887625] [140501292804480] [alembic.runtime.migration] [INFO] Context impl PostgresqlImpl.
[2025-03-07 03:45:53,212] [2887625] [140501292804480] [alembic.runtime.migration] [INFO] Generating static SQL
[2025-03-07 03:45:53,212] [2887625] [140501292804480] [alembic.runtime.migration] [INFO] Will assume transactional DDL.
BEGIN;

[2025-03-07 03:45:53,215] [2887625] [140501292804480] [alembic.runtime.migration] [INFO] Running upgrade ecbe7e63f6d9 -> 6f44b7ecd7be, Add tags_alt column and migrate tags data
-- Running upgrade ecbe7e63f6d9 -> 6f44b7ecd7be

ALTER TABLE hbi.hosts ADD COLUMN tags_alt JSONB;

UPDATE hbi.hosts h
        SET tags_alt = sub.tags_alt
        FROM (
            SELECT id, COALESCE(
                (SELECT JSONB_AGG(
                            JSONB_BUILD_OBJECT(
                                'namespace', ns.namespace,
                                'key', k.key,
                                'value', v.value
                            )
                        )
                    FROM JSONB_OBJECT_KEYS(tags) AS ns(namespace),
                        JSONB_EACH(tags -> ns.namespace) AS k(key, value),
                        JSONB_ARRAY_ELEMENTS_TEXT(k.value) AS v(value)),
                '[]'::jsonb
            ) AS tags_alt
            FROM hbi.hosts h
            WHERE (h.system_profile_facts->>'host_type' = 'edge') AND h.tags <> '{}'
        ) AS sub
        WHERE h.id = sub.id;;

[2025-03-07 03:45:53,215] [2887625] [140501292804480] [alembic.runtime.migration] [DEBUG] update ecbe7e63f6d9 to 6f44b7ecd7be
UPDATE hbi.alembic_version SET version_num='6f44b7ecd7be' WHERE hbi.alembic_version.version_num = 'ecbe7e63f6d9';

COMMIT;

[2025-03-07 03:45:53,216] [2887625] [140501292804480] [inventory.lib.handlers] [INFO] Flushing Segmentio queue
[2025-03-07 03:45:53,216] [2887625] [140501292804480] [inventory.lib.handlers] [INFO] Flushing Segmentio queue
