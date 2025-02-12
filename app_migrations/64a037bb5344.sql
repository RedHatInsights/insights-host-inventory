BEGIN;

-- Running upgrade 4f0b36e6cf28 -> 64a037bb5344

ALTER TABLE hbi.hosts ADD COLUMN tags_alt JSONB;

UPDATE hbi.alembic_version SET version_num='64a037bb5344' WHERE hbi.alembic_version.version_num = '4f0b36e6cf28';

COMMIT;
