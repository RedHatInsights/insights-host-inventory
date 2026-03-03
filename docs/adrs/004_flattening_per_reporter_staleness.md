
# 4. Flattening per_reporter_staleness

* Status: **Approved**
* Proposed: Nov 19, 2025
* Accepted: Jan 21, 2026
* Service: Host Inventory

## Context

The `per_reporter_staleness` field in the Host Inventory database currently uses a nested JSON/dictionary structure to store multiple timestamps for each reporter: `last_check_in`, `stale_timestamp`, and `delete_timestamp`.

This structure stores redundant, calculated timestamps directly in the database. This increases the storage size and complexity, and creates a risk of data inconsistency if the calculation logic for derived timestamps changes over time.

## Decision

We will refactor the data storage for host staleness timestamps to a simpler, more compact, **flat dictionary structure**.

The new database structure will store **only the essential timestamp** (`last_check_in`) per reporter:

```json
{
  "reporter_name": "ISO timestamp"
}
```

The derived timestamps (like `stale_timestamp` and `delete_timestamp`) will be calculated **on-the-fly** during API response serialization and Kafka message generation, rather than being stored redundantly in the database.

This change will be implemented behind a new **feature flag** (`FLAG_INVENTORY_FLATTENED_PER_REPORTER_STALENESS`) and is written to be backward compatible.

## Consequences

### Positive

  * **Improved Efficiency and Storage:** By storing only the `last_check_in` timestamp, the database records are simplified and storage size for the staleness field is reduced.
  * **Reduced Complexity and Inconsistency:** Eliminating the storage of derived timestamps prevents data inconsistency that could arise from changes in the calculation logic.
  * **Simplified Writes:** The write logic will be simplified to store only the flat timestamp string when the feature flag is enabled.

### Negative

  * **Increased Read-Time Computation:** Derived timestamps now need to be computed dynamically during every read (API response and Kafka message generation), which adds a slight computational load to the serialization logic.
  * **Backward Compatibility Overhead:** Initial implementation requires refactoring key areas (serialization, host model, DB filters) to support and read **both** the legacy nested and the new flat structure until the full data migration is complete and clean-up can occur.

### Actions

1.  Implement **backward-compatible reads** across serialization (`app/serialization.py`), host logic (`app/models/host.py`), and filtering (`api/filtering/db_filters.py`).
2.  Add logic to **write the flat structure** when the feature flag is enabled.
3.  Introduce a **one-time batch job** (`FlattenPerReporterStalenessJob`) to migrate all existing nested data to the new flat format.
4.  Once the job successfully runs in production, **clean up** the code paths that handle the nested structure.
