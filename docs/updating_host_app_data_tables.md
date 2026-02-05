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
```

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

Ensure you've updated **all** relevant test files. The parametrized tests in `test_host_app_mq_service.py` cover all applications automatically.

### Validation errors in MQ service

Check that your field types in the SQLAlchemy model match the expected types from the Kafka message. The MQ service validates incoming data before inserting.
