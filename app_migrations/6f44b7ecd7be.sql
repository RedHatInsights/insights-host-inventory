BEGIN;

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

UPDATE hbi.alembic_version SET version_num='6f44b7ecd7be' WHERE hbi.alembic_version.version_num = 'ecbe7e63f6d9';

COMMIT;
