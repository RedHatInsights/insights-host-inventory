BEGIN;

-- Running upgrade 286343296975 -> 64a037bb5344

ALTER TABLE hbi.hosts ADD COLUMN tags_alt JSONB;

UPDATE hbi.alembic_version SET version_num='64a037bb5344' WHERE hbi.alembic_version.version_num = '286343296975';

COMMIT;
