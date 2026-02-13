# How to Update Downstream App Tables in HBI

## Overview

This guide outlines the process for modifying tables related to downstream applications (e.g., `hosts_app_data_patch`, `hosts_app_data_malware`) within the HBI service. These changes are typically required when a downstream app introduces new data fields or modifies existing data structures.

The Host App Data tables are used by the Inventory Views feature to store application-specific data for each host. Data flows from downstream services via Kafka messages on the `platform.inventory.host-apps` topic.

## Affected Files

To ensure end-to-end consistency, you must update the following files:

| File | Purpose |
|------|---------|
| `app/models/host_app_data.py` | SQLAlchemy model definition |
| `app/queue/enums.py` | Application enum (if adding a new app) |
| `swagger/host_app_events.spec.yaml` | Event schema specification |
| `tests/test_host_app_mq_service.py` | MQ service integration tests |
| `tests/test_models.py` | Database model unit tests |
| `api/filtering/app_data_sorting.py` | Sorting logic for hosts-view endpoint |
| `tests/test_api_host_views.py` | Hosts-view API tests (including sorting) |
| `tests/test_filtering_app_data_sorting.py` | Sorting utility unit tests |

## Step-by-Step Guide

### 1. Update the Database Model

Modify the SQLAlchemy model definition to reflect the new table structure.

**File:** `app/models/host_app_data.py`

**Action:** Add, remove, or modify columns in the relevant class.

**Example:** Adding a new field to `HostAppDataPatch`:

```python
class HostAppDataPatch(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_patch"
    __app_name__ = "patch"

    # Existing fields...
    advisories_rhsa_applicable = db.Column(db.Integer, nullable=True)
    advisories_rhba_applicable = db.Column(db.Integer, nullable=True)
    # ... more existing fields ...

    # NEW: Add your new field here
    my_new_field = db.Column(db.String(255), nullable=True)

    # NEW: If the field should be sortable in hosts-view, add it to __sortable_fields__
    __sortable_fields__ = (
        "advisories_rhsa_applicable",
        "advisories_rhba_applicable",
        # ... existing sortable fields ...
        "my_new_field",  # Add your new field here
    )
```

#### Enabling Sorting via `__sortable_fields__`

The `HostAppDataMixin` base class defines an optional `__sortable_fields__` class attribute. Fields listed in this tuple can be used for sorting in the `/beta/hosts-view` endpoint via the `order_by` query parameter using the `app_name:field_name` format.

**Default:** `__sortable_fields__` defaults to an empty tuple `()`, meaning no fields are sortable unless explicitly declared.

**Example:** To allow sorting by `my_new_field` in the Patch app:

```python
class HostAppDataPatch(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_patch"
    __app_name__ = "patch"
    __sortable_fields__ = (
        "advisories_rhsa_installable",
        # ... other fields ...
        "my_new_field",  # Enables: ?order_by=patch:my_new_field
    )

    my_new_field = db.Column(db.Integer, nullable=True)
```

The sort field map in `api/filtering/app_data_sorting.py` is built dynamically from all models' `__sortable_fields__` declarations, so no additional registration is needed.

**Currently supported sortable fields by application:**

| Application | Sortable Fields |
|-------------|----------------|
| `advisor` | `recommendations`, `incidents` |
| `vulnerability` | `total_cves`, `critical_cves`, `high_severity_cves`, `cves_with_security_rules`, `cves_with_known_exploits` |
| `patch` | `advisories_rhsa_installable`, `advisories_rhba_installable`, `advisories_rhea_installable`, `advisories_other_installable`, `advisories_rhsa_applicable`, `advisories_rhba_applicable`, `advisories_rhea_applicable`, `advisories_other_applicable`, `packages_installable`, `packages_applicable`, `packages_installed` |
| `remediations` | `remediations_plans` |
| `compliance` | `last_scan` |
| `malware` | `last_matches`, `total_matches`, `last_scan` |

**Usage in the API:**

```
GET /api/inventory/v1/beta/hosts-view?order_by=patch:my_new_field&order_how=DESC
```

> **Note:** Hosts without app data for the sorted field will appear at the end of the results regardless of sort direction (`NULLS LAST` behavior). Only `db.Integer` and `db.DateTime` columns are recommended for sorting. String and JSONB columns are typically not suitable sort candidates.

**Supported Column Types:**
- `db.Integer` - For numeric counts
- `db.String(length)` - For text with max length
- `UUID(as_uuid=True)` - For UUID fields
- `db.DateTime(timezone=True)` - For timestamps
- `JSONB` - For complex JSON structures (e.g., arrays, nested objects)

> **Note:** All fields should typically be `nullable=True` since downstream services may not always provide every field.

### 2. Update the Event Schema

Update the Kafka event schema to document the new fields.

**File:** `swagger/host_app_events.spec.yaml`

**Action:** Add the corresponding field definitions to the appropriate `*Data` schema.

**Example:** Adding a field to `PatchData`:

```yaml
PatchData:
  description: Patch application data
  type: object
  properties:
    installable_advisories:
      type: integer
      description: Number of installable advisories
    template:
      type: string
      maxLength: 255
      description: Patch template name
    # NEW: Add your new field here
    my_new_field:
      type: string
      maxLength: 255
      description: Description of my new field
```

### 3. Update the Application Enum (New Apps Only)

If you are adding support for a **new** downstream application, register it in the enum.

**File:** `app/queue/enums.py`

**Action:** Add a new value to `ConsumerApplication`:

```python
class ConsumerApplication(StrEnum):
    ADVISOR = "advisor"
    VULNERABILITY = "vulnerability"
    PATCH = "patch"
    # ... existing apps ...
    MY_NEW_APP = "my_new_app"  # NEW: Add your app here
```

### 4. Generate Database Migration

Create the Alembic migration script to apply your changes to the database.

**Command:**

```bash
make migrate_db message "Add my_new_field to hosts_app_data_patch"
```

> **Note:** Always review the generated migration file in `migrations/versions/` to ensure the `upgrade()` and `downgrade()` functions contain only the changes you intended.

**Example of a clean migration:**

```python
def upgrade():
    op.add_column(
        'hosts_app_data_patch',
        sa.Column('my_new_field', sa.String(length=255), nullable=True),
        schema='hbi'
    )

def downgrade():
    op.drop_column('hosts_app_data_patch', 'my_new_field', schema='hbi')
```

### 5. Update Tests

You **must** update the test suite to account for the new schema. Failure to do so will cause CI/CD failures.

#### A. Update MQ Service Tests

**File:** `tests/test_host_app_mq_service.py`

**Action:** Update the `APPLICATION_TEST_DATA` list to include your new fields in the mock payloads.

**Example:**

```python
APPLICATION_TEST_DATA = [
    # ... existing test data ...
    pytest.param(
        ConsumerApplication.PATCH,
        HostAppDataPatch,
        {
            "advisories_rhsa_applicable": 10,
            "advisories_rhba_applicable": 5,
            "my_new_field": "test_value",  # NEW: Add your field here
        },
        {
            "advisories_rhsa_applicable": 10,
            "advisories_rhba_applicable": 5,
            "my_new_field": "test_value",  # NEW: Add to verification dict
        },
        id="patch",
    ),
]
```

#### B. Update Model Tests

**File:** `tests/test_models.py`

**Action:** Add or update test cases to verify that your new columns can be written to and read from the database correctly.

**Example:**

```python
def test_create_host_app_data_patch(db_create_host):
    """Test creating a HostAppDataPatch record."""
    host = db_create_host()
    current_time = now()

    patch_data = HostAppDataPatch(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        advisories_rhsa_applicable=10,
        my_new_field="test_value",  # NEW: Test your field
    )
    db.session.add(patch_data)
    db.session.commit()

    retrieved = db.session.query(HostAppDataPatch).filter_by(
        org_id=host.org_id, host_id=host.id
    ).first()

    assert retrieved is not None
    assert retrieved.my_new_field == "test_value"  # NEW: Verify your field
```

#### C. Update Sorting Tests (if `__sortable_fields__` was modified)

If you added or changed `__sortable_fields__`, update the sorting tests.

**File:** `tests/test_api_host_views.py`

**Action:** Add test cases to verify sorting behavior for the new fields in the hosts-view endpoint.

**Example:**

```python
def test_sort_by_my_new_app_field(
    api_get,
    db_create_host,
    db_create_host_app_data,
):
    """Verify sorting by my_app:field_one in the hosts-view endpoint."""
    host_a = db_create_host()
    host_b = db_create_host()

    db_create_host_app_data(host_a, "my_app", {"field_one": 100})
    db_create_host_app_data(host_b, "my_app", {"field_one": 5})

    # Ascending sort
    response = api_get(
        HOST_VIEWS_URL,
        query_string={"order_by": "my_app:field_one", "order_how": "ASC"},
    )
    assert response["results"][0]["id"] == str(host_b.id)
    assert response["results"][1]["id"] == str(host_a.id)
```

**File:** `tests/test_filtering_app_data_sorting.py`

**Action:** Verify that the new field appears in the sort field map.

```python
def test_my_app_field_in_sort_map():
    sort_map = get_app_sort_field_map()
    assert "my_app:field_one" in sort_map
```

### 6. Apply and Verify

Apply the migration locally and run the test suite to verify your changes.

```bash
# Apply the migration
make upgrade_db

# Run all tests
pytest .

# Or run specific test files
pytest tests/test_host_app_mq_service.py tests/test_models.py -v
```

## Quick Reference: Adding a New Application

If you're adding an entirely new downstream application (not just modifying an existing one), follow these additional steps:

1. **Create the model class** in `app/models/host_app_data.py`:

```python
class HostAppDataMyApp(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_my_app"
    __app_name__ = "my_app"
    __sortable_fields__ = ("field_one",)  # Optional: enable sorting on numeric/datetime fields

    field_one = db.Column(db.Integer, nullable=True)
    field_two = db.Column(db.String(255), nullable=True)
```

2. **Add the enum value** in `app/queue/enums.py`

3. **Add the schema definition** in `swagger/host_app_events.spec.yaml`

4. **Update the `oneOf` list** in `swagger/host_app_events.spec.yaml` under `HostAppItem.data`

5. **Add comprehensive tests** for the new application

6. **Generate and verify the migration**

## Troubleshooting

### Tests fail with missing field errors

Ensure you've updated **all** relevant test files. The parameterized tests in `test_host_app_mq_service.py` cover all applications automatically.

### Validation errors in MQ service

Check that your field types in the SQLAlchemy model match the expected types from the Kafka message. The MQ service validates incoming data before inserting.
