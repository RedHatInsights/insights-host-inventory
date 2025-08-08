"""Drop obsolete foreign key from hosts_groups_old table

Revision ID: 96e12ae08c05
Revises: 3b60b7daf0f2
Create Date: 2025-08-07 14:24:21.101543

"""

from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "96e12ae08c05"
down_revision = "3b60b7daf0f2"
branch_labels = None
depends_on = None

OLD_TABLE_NAME = "hosts_groups_old"
FK_NAME = "hosts_groups_group_id_fkey"


def upgrade():
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM pg_tables
                WHERE schemaname = '{INVENTORY_SCHEMA}' AND tablename = '{OLD_TABLE_NAME}'
            ) THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    WHERE rel.relname = '{OLD_TABLE_NAME}'
                      AND con.conname = '{FK_NAME}'
                      AND con.connamespace = (
                          SELECT oid FROM pg_namespace WHERE nspname = '{INVENTORY_SCHEMA}'
                      )
                ) THEN
                    RAISE NOTICE 'Foreign key "{FK_NAME}" found on table "{OLD_TABLE_NAME}". Dropping it.';
                    ALTER TABLE {INVENTORY_SCHEMA}.{OLD_TABLE_NAME} DROP CONSTRAINT {FK_NAME};
                ELSE
                    RAISE NOTICE 'Foreign key "{FK_NAME}" not found on table "{OLD_TABLE_NAME}". No action needed.';
                END IF;
            ELSE
                RAISE NOTICE 'Table "{OLD_TABLE_NAME}" not found. No action needed.';
            END IF;
        END;
        $$;
    """)


def downgrade():
    # DO NOTHING. We don't want to re-create a FK on an unused table.
    pass
