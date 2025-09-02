# inv_publish_hosts.py Configuration

This document describes the configuration options available for the `jobs/inv_publish_hosts.py` script.

## Environment Variables

### CREATE_PUBLICATIONS
- **Type**: Comma-separated string
- **Default**: `""` (empty - no publications created by default)
- **Description**: List of PostgreSQL publications to create.
- **Example**: `"hbi_hosts_pub_v1_0_2,hbi_hosts_pub_v2_0_0"`
- **Note**: Each publication must exist as a key in the internal `PUBLICATION_CONFIG` structure
- **Control**: Use empty string to skip publication creation entirely

### DROP_PUBLICATIONS
- **Type**: Comma-separated string
- **Default**: `""` (empty - no publications dropped by default)
- **Description**: List of legacy publication names to drop before creating new ones.
- **Example**: `"old_pub1,legacy_pub2,deprecated_pub3"`
- **Control**: Use empty string to skip publication dropping entirely

### DROP_REPLICATION_SLOTS
- **Type**: Comma-separated string
- **Default**: `""` (empty - no replication slots dropped by default)
- **Description**: List of replication slot names to drop if they are inactive.
- **Example**: `"slot1,slot2,slot3"`
- **Note**: Empty string or unset means no replication slots will be dropped

### REPLICA_IDENTITY_MODE
- **Type**: String
- **Default**: `""` (empty - no changes will be made to the replica identity)
- **Valid values**: `"default"`, `"index"`, `""` (empty string)
- **Description**: Sets the replica identity mode for all tables and their partitions.
  - `"default"`: Uses PostgreSQL's default replica identity (usually primary key)
  - `"index"`: Uses a unique index for replica identity
  - `""` (empty string): Skip replica identity configuration entirely
- **Smart Detection**: The script efficiently checks each table's current replica identity using PostgreSQL's `regclass` functionality before making changes. Tables already in the desired mode are skipped, reducing unnecessary operations.

## Tables Managed

All tables are configured in the `PUBLICATION_CONFIG` variable within the script, which includes:
- Publication name (as top-level key)
- Tables list for each publication containing:
  - Table name
  - Schema name
  - Partition information
  - Publication columns
  - Publication filter (WHERE clause for selective replication)

This structure supports multiple publications and makes it easy to modify table configurations, add new publications, update schemas, change publication columns, or customize replication filters as needed.

### Adding New Publications

To add a new publication, simply add a new key to `PUBLICATION_CONFIG` in the script:

```python
PUBLICATION_CONFIG = {
    "hbi_hosts_pub_v1_0_2": {
        "tables": [
            # ... existing tables
        ]
    },
    "hbi_hosts_pub_v2_0_0": {  # New publication
        "tables": [
            {
                "name": "hosts",
                "schema": INVENTORY_SCHEMA,
                "has_partitions": True,
                "publication_columns": ["org_id", "id", "display_name"],  # Different columns
                "publication_filter": "created_on > '2024-01-01'"  # Different filter
            },
            # ... other tables with different configurations
        ]
    }
}
```

Then specify both publications in the environment variable:
```bash
CREATE_PUBLICATIONS="hbi_hosts_pub_v1_0_2,hbi_hosts_pub_v2_0_0"
```

## Control Mechanism

The script uses **empty values** to control whether operations are performed:

- **`CREATE_PUBLICATIONS=""` (empty)**: Skip publication creation entirely
- **`DROP_PUBLICATIONS=""` (empty)**: Skip publication dropping entirely
- **`DROP_REPLICATION_SLOTS=""` (empty)**: Skip replication slot cleanup entirely
- **`REPLICA_IDENTITY_MODE=""` (empty)**: Skip replica identity configuration entirely

This provides fine-grained control without needing separate enable/disable flags. You can selectively enable/disable each type of operation independently.

## Usage Examples

### Basic usage (default configuration)
```bash
python jobs/inv_publish_hosts.py
```

### Skip replica identity configuration
```bash
REPLICA_IDENTITY_MODE="" python jobs/inv_publish_hosts.py
```

### Skip all operations (publications and replica identity)
```bash
CREATE_PUBLICATIONS="" DROP_PUBLICATIONS="" DROP_REPLICATION_SLOTS="" REPLICA_IDENTITY_MODE="" python jobs/inv_publish_hosts.py
```

### Full custom configuration
```bash
CREATE_PUBLICATIONS="hbi_hosts_pub_v1_0_2" \
REPLICA_IDENTITY_MODE=index \
DROP_PUBLICATIONS="hbi_hosts_pub_v1_0_0,hbi_hosts_pub_v1_0_1" \
DROP_REPLICATION_SLOTS="roadmap_hosts_sub" \
python jobs/inv_publish_hosts.py
```

## What the Script Does

1. **Replica Identity Configuration**: Sets replica identity for all tables and partitions according to `REPLICA_IDENTITY_MODE`
   - **Smart Detection**: Checks current replica identity before making changes
   - **Skip Unchanged**: Tables already in the desired mode are skipped
   - **Efficient Updates**: Only modifies tables that need changes
   - **Skip Entirely**: Use empty string (`""`) to skip replica identity configuration completely
2. **Publication Management**:
   - Drops legacy publications (if `DROP_PUBLICATIONS` is not empty)
   - Creates each publication from `CREATE_PUBLICATIONS` list if it doesn't exist (if `CREATE_PUBLICATIONS` is not empty)
3. **Replication Slot Cleanup**: Drops inactive replication slots listed in `DROP_REPLICATION_SLOTS`


## Error Handling

- If replica identity mode is invalid, the script logs an error and skips replica identity configuration
- If publication or replication slot operations fail, the transaction is rolled back
- All database changes are committed only if all operations succeed
