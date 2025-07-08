"""add_find_host_by_canonical_facts

Revision ID: 1a07436e7411
Revises: 28280de3f1ce
Create Date: 2025-07-05 10:15:32.973929

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a07436e7411'
down_revision = '28280de3f1ce'
branch_labels = None
depends_on = None


def upgrade():
    # Create the find_host_by_canonical_facts function
    # Potential Future work
    #  -Filter by staleness requirements
    #  -Secondary order by modified
    op.execute("""
        CREATE OR REPLACE FUNCTION public.find_host_by_canonical_facts(
            p_org_id text,
            p_provider_id uuid,
            p_provider_type text,
            p_subscription_manager_id uuid,
            p_insights_id uuid
        ) RETURNS uuid AS
        $$ SELECT COALESCE((SELECT id
                    FROM hbi.hosts
                    WHERE org_id = p_org_id AND (
                       -- First priority: provider_id
                        (canonical_facts @> JSONB_BUILD_OBJECT('provider_id', p_provider_id, 'provider_type', p_provider_type))

                       OR

                       -- Second priority: subscription_manager_id
                        (canonical_facts @> JSONB_BUILD_OBJECT('subscription_manager_id', p_subscription_manager_id))

                       OR

                       -- Third priority: insights_id
                        (canonical_facts @> JSONB_BUILD_OBJECT('insights_id', p_insights_id)))

                    ORDER BY CASE
                                 WHEN canonical_facts ? 'provider_id' THEN 1
                                 WHEN canonical_facts ? 'subscription_manager_id' THEN 2
                                 WHEN canonical_facts ? 'insights_id' THEN 3
                                 END
                    -- Generate a random UUID if no host is found
                    LIMIT 1), gen_random_uuid());
        $$
            LANGUAGE sql STABLE;
    """)


def downgrade():
    # Drop the find_host_by_canonical_facts function
    op.execute("DROP FUNCTION IF EXISTS find_host_by_canonical_facts(text, uuid, text, uuid, uuid);")
