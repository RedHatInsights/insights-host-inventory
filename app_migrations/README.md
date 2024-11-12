# Performing Migrations Against Replicated Tables

This document covers the strategy for perfomring migrations against replicated tables. In most cases its necessary for migrations to be run against replicated tables prior to this action taking place on the publishing database in order to avoid replication errors. Host Based Inventory utilizes [sqlalchemy alembic](https://alembic.sqlalchemy.org/en/latest/) in order to perform migrations. The intended strategy is that for any upcoming migration change would be proceeded with a commit that adds a SQL file containing the result from the [alembic offline mode](https://alembic.sqlalchemy.org/en/latest/offline.html). This migration can then be run by an application team utilizing the Host Based Inventory container image with the specified migration file name (specified by the `INVENTORY_MIGRATION_FILE` environment variable) using a ClowdJobInvocation.

## Directory Contents

The purpose of this directory is to contain `*.sql` files that containt the output from the alembic offline mode.

To generate an offline SQL file from an alembic migration run the following command:

```
make gen_offline_sql down_rev=<downgrade revision> up_rev=<upgrade revision>
```
This will produce a file in the `app_migrations` directory named <upgrade_revision>.sql. You will need to clean up this file to remove the log entries and the update to the alembic version table.

## Local Execution
You can run your migration locally both with a dry run (logging but no execution) and execution as follows.

### Dry run
Provide the dry run environment variable at the command line, in the case below we are using the `query_hbi_schema.sql` migration file present in the `app_migrations` directory.
```
INVENTORY_MIGRATION_DRYRUN="true" INVENTORY_MIGRATION_FILE="query_hbi_schema.sql" python inv_migration_runner.py
```
When this runs you will only see the SQL that would have been executed on the database.

### Execution
In the case below we are using the `query_hbi_schema.sql` migration file present in the `app_migrations` directory.
```
INVENTORY_MIGRATION_FILE="query_hbi_schema.sql" python inv_migration_runner.py
```
When this runs you will see the results of the executed SQL file in the logged output.

## Example ClowdJobInvocation and ClowdApp Migration Runner

You can find a sample ClowdJobInvocation and ClowdApp template in the `/deploy/migration-runner-cji.yml` file.

The critical parameters are:
- DEPENDENT_APP_NAME: The ClowdApp name with the database you will be migrating
- DB_NAME: The shared database name
- INVENTORY_IMAGE_TAG: The insights-inventory image tag with the migration file you want to run
- INVENTORY_MIGRATION_FILE: The name of the SQL file you want to run
- MIGRATION_RUN_NUMBER: The incrementing job number (defaults to 1)
