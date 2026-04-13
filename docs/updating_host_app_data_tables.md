# How to Update Downstream App Tables in HBI

## Overview

This guide outlines the process for modifying tables related to downstream applications (e.g., `hosts_app_data_patch`, `hosts_app_data_malware`) within the HBI service. These changes are typically required when a downstream app introduces new data fields or modifies existing data structures.

The Host App Data tables are used by the Inventory Views feature to store application-specific data for each host. Data flows from downstream services via Kafka messages on the `platform.inventory.host-apps` topic, and is exposed through the `GET /api/inventory/v1/beta/hosts-view` endpoint.

### Inventory Views Endpoint Capabilities

The `/beta/hosts-view` endpoint returns host data combined with application-specific metrics. It supports:

- **Sorting** by app data fields using the `order_by=app:field` format (e.g., `order_by=vulnerability:critical_cves`)
- **Filtering** by app data fields using `filter[app][field][operator]=value` (e.g., `filter[patch][packages_installable][gte]=5`)
- **Sparse fieldsets** to control which application data is included in the response (e.g., `fields[advisor]=recommendations,incidents`)

Downstream apps declare which of their fields support sorting and filtering via `__sortable_fields__` and `__filterable_fields__` on their model class. See the sections below for details.

## Affected Files

To ensure end-to-end consistency, you must update the following files:

| File | Purpose |
|------|---------|
| `app/models/host_app_data.py` | SQLAlchemy model definition (columns, sortable/filterable fields) |
| `app/queue/enums.py` | Application enum (if adding a new app) |
| `swagger/host_app_events.spec.yaml` | Kafka event schema specification |
| `tests/test_host_app_mq_service.py` | MQ service integration tests |
| `tests/test_models.py` | Database model unit tests |
| `api/filtering/app_data_sorting.py` | Sorting logic for hosts-view endpoint |
| `api/filtering/db_app_data_filters.py` | Filtering logic for hosts-view endpoint |
| `tests/test_api_host_views.py` | Hosts-view API tests (sorting, filtering, sparse fields) |
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

    # NEW: If the field should be sortable, add it to __sortable_fields__
    __sortable_fields__ = (
        "advisories_rhsa_applicable",
        "advisories_rhba_applicable",
        # ... existing sortable fields ...
        "my_new_field",  # Add your new field here
    )

    # NEW: If the field should be filterable, add it to __filterable_fields__
    __filterable_fields__ = (
        "advisories_rhsa_applicable",
        "advisories_rhba_applicable",
        # ... existing filterable fields ...
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

The current sortable fields for each application are defined by the `__sortable_fields__` tuples in `app/models/host_app_data.py`. Check each model class for the authoritative list.

**Usage in the API:**

```
GET /api/inventory/v1/beta/hosts-view?order_by=patch:my_new_field&order_how=DESC
```

> **Note:** Hosts without app data for the sorted field will appear at the end of the results regardless of sort direction (`NULLS LAST` behavior). Only `db.Integer` and `db.DateTime` columns are recommended for sorting. String and JSONB columns are typically not suitable sort candidates.

#### Enabling Filtering via `__filterable_fields__`

The `HostAppDataMixin` base class defines an optional `__filterable_fields__` class attribute. Fields listed in this tuple can be used for filtering in the `/beta/hosts-view` endpoint via the `filter` query parameter using the `filter[app_name][field_name][operator]=value` format.

**Default:** `__filterable_fields__` defaults to an empty tuple `()`, meaning no fields are filterable unless explicitly declared.

**Example:** To allow filtering by `my_new_field` in the Patch app:

```python
class HostAppDataPatch(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_patch"
    __app_name__ = "patch"
    __filterable_fields__ = (
        "advisories_rhsa_installable",
        # ... other fields ...
        "my_new_field",  # Enables: ?filter[patch][my_new_field][gte]=10
    )

    my_new_field = db.Column(db.Integer, nullable=True)
```

The filter logic in `api/filtering/db_app_data_filters.py` validates field names against `__filterable_fields__` at runtime, so no additional registration is needed.

**Supported filter operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to | `filter[patch][packages_installable][eq]=10` |
| `ne` | Not equal to | `filter[patch][packages_installable][ne]=0` |
| `gt` | Greater than | `filter[vulnerability][critical_cves][gt]=5` |
| `gte` | Greater than or equal | `filter[vulnerability][critical_cves][gte]=5` |
| `lt` | Less than | `filter[advisor][recommendations][lt]=100` |
| `lte` | Less than or equal | `filter[advisor][recommendations][lte]=100` |
| `nil` | Field is NULL (no data) | `filter[patch][template_name][nil]=true` |
| `not_nil` | Field is not NULL | `filter[patch][template_name][not_nil]=true` |

Multiple filters are combined with AND semantics. You can filter across different apps and fields simultaneously:

```
GET /api/inventory/v1/beta/hosts-view?filter[vulnerability][critical_cves][gt]=0&filter[patch][packages_installable][gte]=5
```

App data filters can also be combined with `filter[system_profile]` filters:

```
GET /api/inventory/v1/beta/hosts-view?filter[system_profile][number_of_cpus][gte]=4&filter[patch][packages_installable][gt]=0
```

The current filterable fields for each application are defined by the `__filterable_fields__` tuples in `app/models/host_app_data.py`. Check each model class for the authoritative list.

> **Note:** Filterable fields can be a superset of sortable fields. For instance, string fields like `template_name` or `last_status` may be filterable (via `eq`/`nil`/`not_nil`) but not sortable.

**Supported Column Types:**
- `db.Integer` - For numeric counts
- `db.String(length)` - For text with max length
- `UUID(as_uuid=True)` - For UUID fields
- `db.DateTime(timezone=True)` - For timestamps
- `JSONB` - For complex JSON structures (e.g., arrays, nested objects)

> **Note:** All fields should typically be `nullable=True` since downstream services may not always provide every field.

#### Sparse Fieldsets in API Responses

The `/beta/hosts-view` endpoint supports JSON:API-style sparse fieldsets via the `fields` query parameter. This allows API consumers to control which application data is included in each host's `app_data` object. This feature works automatically for all fields on any model; no special declaration is needed.

**Usage:**

| Parameter | Behavior |
|-----------|----------|
| *(omitted)* | All apps and all fields are returned (default) |
| `fields[app_data]=true` | All apps and all fields (explicit shorthand) |
| `fields[advisor]=true` | Only advisor data, all fields |
| `fields[advisor]=recommendations,incidents` | Only advisor data, only those two fields |
| `fields[advisor]=&fields[patch]=true` | Advisor with no fields (empty object), Patch with all fields |
| `fields[invalid_app]=true` | Ignored; other valid apps still returned |

**Example:**

```
GET /api/inventory/v1/beta/hosts-view?fields[advisor]=recommendations&fields[vulnerability]=critical_cves,total_cves
```

Response `app_data` will only contain `advisor` and `vulnerability` keys, with only the requested fields in each.

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

#### D. Update Filtering Tests (if `__filterable_fields__` was modified)

If you added or changed `__filterable_fields__`, update the filtering tests.

**File:** `tests/test_api_host_views.py`

**Action:** Add test cases to verify filtering behavior for the new fields. Test at least the basic operators (`eq`, `nil`, `not_nil`) and, for numeric fields, comparison operators (`gt`, `gte`, `lt`, `lte`).

**Example:**

```python
def test_filter_by_my_new_app_field(
    api_get,
    db_create_host,
    db_create_host_app_data,
):
    """Verify filtering by my_app:field_one in the hosts-view endpoint."""
    host_a = db_create_host()
    host_b = db_create_host()

    db_create_host_app_data(host_a, "my_app", {"field_one": 100})
    db_create_host_app_data(host_b, "my_app", {"field_one": 5})

    # Filter: field_one >= 50
    response = api_get(
        HOST_VIEWS_URL,
        query_string={"filter[my_app][field_one][gte]": "50"},
    )
    assert response["total"] == 1
    assert response["results"][0]["id"] == str(host_a.id)
```

**Action:** Also test that filtering and sorting work together for the same app.

```python
def test_filter_and_sort_same_app(
    api_get,
    db_create_host,
    db_create_host_app_data,
):
    """Verify filter + sort on the same app field."""
    host_a = db_create_host()
    host_b = db_create_host()
    host_c = db_create_host()

    db_create_host_app_data(host_a, "my_app", {"field_one": 100})
    db_create_host_app_data(host_b, "my_app", {"field_one": 50})
    db_create_host_app_data(host_c, "my_app", {"field_one": 5})

    response = api_get(
        HOST_VIEWS_URL,
        query_string={
            "filter[my_app][field_one][gte]": "10",
            "order_by": "my_app:field_one",
            "order_how": "DESC",
        },
    )
    assert response["total"] == 2
    assert response["results"][0]["id"] == str(host_a.id)
    assert response["results"][1]["id"] == str(host_b.id)
```

#### E. Update Sparse Fieldset Tests (if adding a new app)

If you added a new application, verify it works with the sparse fieldsets feature.

**File:** `tests/test_api_host_views.py`

**Action:** Add test cases to verify the new app data appears correctly with the `fields` parameter.

```python
def test_sparse_fields_my_new_app(
    api_get,
    db_create_host,
    db_create_host_app_data,
):
    """Verify sparse fieldsets for my_app."""
    host = db_create_host()
    db_create_host_app_data(host, "my_app", {"field_one": 100, "field_two": "value"})

    # Request only field_one
    response = api_get(
        HOST_VIEWS_URL,
        query_string={"fields[my_app]": "field_one"},
    )
    app_data = response["results"][0]["app_data"]["my_app"]
    assert "field_one" in app_data
    assert "field_two" not in app_data
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
    __filterable_fields__ = ("field_one", "field_two")  # Optional: enable filtering

    field_one = db.Column(db.Integer, nullable=True)
    field_two = db.Column(db.String(255), nullable=True)
```

2. **Add the enum value** in `app/queue/enums.py`

3. **Add the schema definition** in `swagger/host_app_events.spec.yaml`

4. **Update the `oneOf` list** in `swagger/host_app_events.spec.yaml` under `HostAppItem.data`

5. **Add comprehensive tests** for the new application (MQ, model, sorting, filtering, sparse fields)

6. **Generate and verify the migration**

## Troubleshooting

### Tests fail with missing field errors

Ensure you've updated **all** relevant test files. The parameterized tests in `test_host_app_mq_service.py` cover all applications automatically.

### Validation errors in MQ service

Check that your field types in the SQLAlchemy model match the expected types from the Kafka message. The MQ service validates incoming data before inserting.

### Filter returns 400 "Invalid filter field"

The field must be listed in `__filterable_fields__` on the model class. Only explicitly declared fields are allowed. Check `app/models/host_app_data.py` for the current allowlist.

### Sort returns 400 "Unsupported app sort field"

The field must be listed in `__sortable_fields__` on the model class. The error message includes the full list of allowed sort fields.

### Sparse fieldsets return empty `app_data`

If `fields[app]=` (empty value) is passed, the endpoint intentionally returns an empty object for that app per JSON:API spec. Use `fields[app]=true` to request all fields, or specify field names explicitly.
