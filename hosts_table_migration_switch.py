#!/usr/bin/python
# ruff: noqa: E501
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "hosts-table-migration-switch"
LOGGER_NAME = "hosts_table_migration_switch"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

"""
This job performs the final, atomic cutover to the new partitioned tables
OR rolls back the change if necessary.

The behavior is controlled by the `HOSTS_TABLE_MIGRATION_SWITCH_MODE` environment variable:
- `switch` (default): Performs the forward migration, making the new tables live.
- `rollback`: Reverts the switch, making the old tables live again.

This script should only be run during a planned maintenance window.
"""


def perform_action(session: Session, logger: Logger):
    """
    Executes either the switch or rollback operation based on an environment variable.
    """
    action = os.environ.get("HOSTS_TABLE_MIGRATION_SWITCH_MODE", "switch").lower()

    if action == "switch":
        logger.info("HOSTS_TABLE_MIGRATION_SWITCH_MODE=switch. Starting the final table switch operation...")
        sql_block = f"""
            DO $$
            BEGIN
                -- Set a local timeout for this transaction only.
                -- If it can't get a lock within 60 seconds, it will error out.
                SET LOCAL lock_timeout = '60s';

                -- Lock all tables involved in the swap
                RAISE NOTICE 'Acquiring exclusive locks on all tables...';
                LOCK TABLE {INVENTORY_SCHEMA}.hosts IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_new IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups_new IN ACCESS EXCLUSIVE MODE;

                -- Rename old tables' primary key constraints to free up names
                RAISE NOTICE 'Renaming old constraints...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_pkey TO hosts_old_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME CONSTRAINT hosts_groups_pkey TO hosts_groups_old_pkey;

                -- Rename old tables to keep them as backups
                RAISE NOTICE 'Renaming old tables...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME TO hosts_old;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME TO hosts_groups_old;

                -- Rename new tables to their final production names
                RAISE NOTICE 'Renaming new tables...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_new RENAME TO hosts;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups_new RENAME TO hosts_groups;

                -- Rename new tables' primary key constraints to their final production names
                RAISE NOTICE 'Renaming new constraints...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_new_pkey TO hosts_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME CONSTRAINT hosts_groups_new_pkey TO hosts_groups_pkey;
            END;
            $$;
        """
        session.execute(text(sql_block))
        logger.info("Successfully switched to new partitioned tables.")

    elif action == "rollback":
        logger.warning("HOSTS_TABLE_MIGRATION_SWITCH_MODE=rollback. Starting rollback procedure...")
        sql_block = f"""
            DO $$
            BEGIN
                -- Set a local timeout for this transaction only.
                -- If it can't get a lock within 60 seconds, it will error out.
                SET LOCAL lock_timeout = '60s';

                -- Lock all tables involved in the swap
                RAISE NOTICE 'Acquiring exclusive locks on all tables for rollback...';
                LOCK TABLE {INVENTORY_SCHEMA}.hosts IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_old IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups_old IN ACCESS EXCLUSIVE MODE;

                -- Rename current tables' constraints back to their temporary names
                RAISE NOTICE 'Renaming current constraints...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_pkey TO hosts_new_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME CONSTRAINT hosts_groups_pkey TO hosts_groups_new_pkey;

                -- Rename current tables back to their temporary names
                RAISE NOTICE 'Renaming current tables...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME TO hosts_new;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME TO hosts_groups_new;

                -- Rename old tables back to their production names
                RAISE NOTICE 'Renaming old tables back to production...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_old RENAME TO hosts;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups_old RENAME TO hosts_groups;

                -- Rename old tables' constraints back to their production names
                RAISE NOTICE 'Renaming old constraints back to production...';
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_old_pkey TO hosts_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME CONSTRAINT hosts_groups_old_pkey TO hosts_groups_pkey;
            END;
            $$;
        """
        session.execute(text(sql_block))
        logger.info("Successfully rolled back to the original unpartitioned tables.")
    else:
        raise ValueError(f"Invalid HOSTS_TABLE_MIGRATION_SWITCH_MODE: '{action}'. Must be 'switch' or 'rollback'.")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    with application.app.app_context():
        # The session_guard ensures the entire operation is one atomic transaction.
        with session_guard(session):
            perform_action(session, logger)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Hosts tables switch/rollback"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)
