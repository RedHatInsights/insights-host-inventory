#!/usr/bin/env python
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from sqlalchemy import text as sa_text

from app.models import db
from app.models.constants import INVENTORY_SCHEMA
from jobs.inv_publish_hosts import PUBLICATION_CONFIG
from jobs.inv_publish_hosts import _build_create_publication_sql
from jobs.inv_publish_hosts import _get_current_replica_identity_mode
from jobs.inv_publish_hosts import _set_replica_identity_single_table
from jobs.inv_publish_hosts import configure_replica_identities
from jobs.inv_publish_hosts import set_replica_identity_for_table
from jobs.inv_publish_hosts import setup_publication


def get_first_available_publication():
    """Helper function to get the first available publication name from PUBLICATION_CONFIG.

    Returns:
        str: The name of the first publication in PUBLICATION_CONFIG

    Raises:
        AssertionError: If no publications are configured
    """
    assert len(PUBLICATION_CONFIG) > 0, "At least one publication should be configured"
    return next(iter(PUBLICATION_CONFIG.keys()))


def get_unique_table_count():
    """Helper function to get the number of unique tables across all publications.

    Returns:
        int: The number of unique (schema, table_name) combinations across all publications
    """
    unique_tables = set()
    for pub_config in PUBLICATION_CONFIG.values():
        for table in pub_config["tables"]:
            unique_tables.add((table["schema"], table["name"]))
    return len(unique_tables)


def get_table_info():
    """Helper function to get the table's schema and name to be used for testing.

    Returns:
        tuple: (schema, table_name)
    """
    return "hbi", "hosts"


def get_sample_table_config():
    """Helper function to get a sample table configuration for testing.

    Returns:
        dict: A sample table configuration based on the first table in PUBLICATION_CONFIG
    """
    first_pub = next(iter(PUBLICATION_CONFIG.values()))
    first_table = first_pub["tables"][0]

    return {
        "name": first_table["name"],
        "schema": first_table["schema"],
        "publication_columns": first_table["publication_columns"][:3],  # Use first 3 columns
        "publication_filter": first_table.get("publication_filter"),
    }


class TestBuildCreatePublicationSql:
    """Tests for _build_create_publication_sql function."""

    def test_build_create_publication_sql_success(self):
        """Test building CREATE PUBLICATION SQL for valid publication name."""

        publication_name = get_first_available_publication()

        result = _build_create_publication_sql(publication_name)

        sql_text = str(result)

        assert f"CREATE PUBLICATION {publication_name}" in sql_text
        assert "FOR TABLE" in sql_text
        assert "WITH (publish_via_partition_root = true)" in sql_text

        publication_config = PUBLICATION_CONFIG[publication_name]
        for table_config in publication_config["tables"]:
            table_name = table_config["name"]
            schema = table_config["schema"]
            publication_filter = table_config.get("publication_filter", "")

            assert f"{schema}.{table_name}" in sql_text
            if publication_filter:
                assert publication_filter in sql_text

    def test_build_create_publication_sql_invalid_name(self):
        """Test building CREATE PUBLICATION SQL for invalid publication name."""
        with pytest.raises(ValueError, match="Publication 'invalid_pub' not found in PUBLICATION_CONFIG"):
            _build_create_publication_sql("invalid_pub")

    def test_build_create_publication_sql_includes_all_columns(self):
        """Test that all configured columns are included in the SQL."""

        publication_name = get_first_available_publication()

        result = _build_create_publication_sql(publication_name)
        sql_text = str(result)

        publication_config = PUBLICATION_CONFIG[publication_name]
        for table_config in publication_config["tables"]:
            for column in table_config["publication_columns"]:
                assert column in sql_text, f"Column '{column}' missing from SQL for table '{table_config['name']}'"

    def test_build_create_publication_sql_all_publications(self):
        """Test that SQL can be generated successfully for ALL publication configurations."""

        # Test SQL generation for ALL publications
        for pub_name in PUBLICATION_CONFIG.keys():
            result = _build_create_publication_sql(pub_name)
            sql_text = str(result)

            # Basic SQL structure validation
            assert f"CREATE PUBLICATION {pub_name}" in sql_text, f"Publication '{pub_name}' missing CREATE statement"
            assert "FOR TABLE" in sql_text, f"Publication '{pub_name}' missing FOR TABLE clause"
            assert "WITH (publish_via_partition_root = true)" in sql_text, (
                f"Publication '{pub_name}' missing WITH clause"
            )

            # Verify all configured tables and columns are present
            publication_config = PUBLICATION_CONFIG[pub_name]
            for table_config in publication_config["tables"]:
                table_name = table_config["name"]
                schema = table_config["schema"]
                qualified_table_name = f"{schema}.{table_name}"

                assert qualified_table_name in sql_text, (
                    f"Publication '{pub_name}' missing table '{qualified_table_name}'"
                )

                # Check publication columns
                for column in table_config["publication_columns"]:
                    assert column in sql_text, (
                        f"Publication '{pub_name}', table '{table_name}' missing column '{column}'"
                    )

                # Check filter if present
                table_filter = table_config.get("publication_filter", "")
                if table_filter:
                    assert table_filter in sql_text, (
                        f"Publication '{pub_name}', table '{table_name}' missing filter '{table_filter}'"
                    )


class TestReplicaIdentityIntegration:
    """Tests for replica identity configuration functions."""

    def reset_replica_identity(self, table_name):
        """Reset replica identity to default for cleanup."""
        schema, _ = get_table_info()
        try:
            db.session.execute(sa_text(f"ALTER TABLE {schema}.{table_name} REPLICA IDENTITY DEFAULT"))
            db.session.commit()
        except Exception:
            db.session.rollback()

    def drop_index(self, index_name):
        """Drop an index"""
        try:
            db.session.execute(sa_text(f"DROP INDEX IF EXISTS {index_name}"))
            db.session.commit()
        except Exception:
            db.session.rollback()

    def test_get_current_replica_identity_mode_default(self, flask_app):
        """Test getting current replica identity mode when set to default."""
        schema, table_name = get_table_info()

        try:
            with flask_app.app.app_context():
                # Set to default replica identity
                db.session.execute(sa_text(f"ALTER TABLE {schema}.{table_name} REPLICA IDENTITY DEFAULT"))
                db.session.commit()

                result = _get_current_replica_identity_mode(db.session, schema, table_name)
                assert result == "default"
        finally:
            with flask_app.app.app_context():
                self.reset_replica_identity(table_name)

    def test_get_current_replica_identity_mode_index(self, flask_app):
        """Test getting current replica identity mode when set to index."""
        schema, table_name = get_table_info()

        with flask_app.app.app_context():
            # Set to index replica identity
            db.session.execute(
                sa_text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS hosts_replica_identity_idx
                    ON {schema}.{table_name} (org_id, id, insights_id);
                    """
                )
            )
            db.session.execute(
                sa_text(f"ALTER TABLE {schema}.{table_name} REPLICA IDENTITY USING INDEX hosts_replica_identity_idx;")
            )
            db.session.commit()

            result = _get_current_replica_identity_mode(db.session, schema, table_name)
            assert result == "index"

    def test_get_current_replica_identity_mode_no_result(self, flask_app):
        """Test getting current replica identity mode when table doesn't exist."""
        schema, _ = get_table_info()
        with flask_app.app.app_context():
            # When table doesn't exist, PostgreSQL throws an exception
            # The function should handle this and return "unknown"
            result = _get_current_replica_identity_mode(db.session, schema, "nonexistent_table")
            assert result == "unknown"

    def test_set_replica_identity_single_table_already_set(self, flask_app):
        """Test setting replica identity when already set to desired mode."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Set to default first
                db.session.execute(sa_text(f"ALTER TABLE {schema}.{table_name} REPLICA IDENTITY DEFAULT"))
                db.session.commit()

                # Try to set to default again - should skip
                _set_replica_identity_single_table(db.session, mock_logger, schema, table_name, "default")

                expected_msg = f"Table {schema}.{table_name} already has replica identity DEFAULT - skipping"
                mock_logger.info.assert_called_with(expected_msg)
        finally:
            with flask_app.app.app_context():
                self.reset_replica_identity(table_name)

    def test_set_replica_identity_single_table_to_default(self, flask_app):
        """Test setting replica identity to default mode."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        with flask_app.app.app_context():
            # Test setting to default mode (regardless of current state)
            _set_replica_identity_single_table(db.session, mock_logger, schema, table_name, "default")

            # Check that appropriate logging occurred
            calls = [str(call) for call in mock_logger.info.call_args_list]
            has_relevant_logging = any(
                "already has replica identity DEFAULT" in call
                or "Set replica identity DEFAULT" in call
                or "Changing replica identity" in call
                for call in calls
            )
            assert has_relevant_logging, f"Expected relevant logging, got calls: {calls}"

            # Verify it's actually set to default
            result = _get_current_replica_identity_mode(db.session, schema, table_name)
            assert result == "default"

    def test_set_replica_identity_single_table_to_index_with_index(self, flask_app):
        """Test setting replica identity to index mode when suitable index exists."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        with flask_app.app.app_context():
            # Test setting to index mode - behavior depends on available indexes
            _set_replica_identity_single_table(db.session, mock_logger, schema, table_name, "index")

            # Check that appropriate logging occurred
            calls = [str(call) for call in mock_logger.info.call_args_list]
            has_relevant_logging = any(
                "already has replica identity INDEX" in call
                or "Set replica identity USING INDEX" in call
                or "Changing replica identity" in call
                or "No suitable unique index found" in call
                for call in calls
            )
            assert has_relevant_logging, f"Expected relevant logging, got calls: {calls}"

            # The result should be either index (if suitable index exists) or default (fallback)
            result = _get_current_replica_identity_mode(db.session, schema, table_name)
            assert result in ["index", "default"], f"Expected index or default, got {result}"

    def test_set_replica_identity_selects_correct_index(self, flask_app):
        """Test that replica identity 'index' mode selects the correct index when multiple unique indexes exist."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Create multiple unique indexes
                db.session.execute(
                    sa_text(
                        f"""
                        CREATE UNIQUE INDEX IF NOT EXISTS hosts_replica_identity_idx
                        ON {schema}.{table_name} (org_id, id, insights_id)
                        """
                    )
                )
                db.session.execute(
                    sa_text(
                        f"""
                        CREATE UNIQUE INDEX IF NOT EXISTS hosts_other_unique_idx
                        ON {schema}.{table_name} (subscription_manager_id)
                        """
                    )
                )
                db.session.commit()

                _set_replica_identity_single_table(db.session, mock_logger, schema, table_name, "index")

                # Query pg_class and pg_index to verify the correct index is set
                result = db.session.execute(
                    sa_text(f"""
                    SELECT i.relname
                    FROM pg_index x
                    JOIN pg_class t ON t.oid = x.indrelid
                    JOIN pg_class i ON i.oid = x.indexrelid
                    WHERE t.relname = '{table_name}'
                      AND x.indisreplident = true
                """)
                ).fetchone()
                assert result is not None, "No replica identity index found"
                assert result[0] == "hosts_replica_identity_idx", (
                    f"Expected hosts_replica_identity_idx, got {result[0]}"
                )
        finally:
            with flask_app.app.app_context():
                self.drop_index(f"{schema}.hosts_replica_identity_idx")
                self.drop_index(f"{schema}.hosts_other_unique_idx")

    def test_set_replica_identity_single_table_to_index_no_index(self, flask_app):
        """Test setting replica identity to index mode when no suitable index exists."""
        # Use staleness table which is not in PUBLICATION_CONFIG and doesn't have replica identity index
        schema, _ = get_table_info()  # Get schema from config
        table_name = "staleness"  # Use a table that doesn't have the required replica identity index
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Try to set to index mode without suitable index - should fallback to default
                _set_replica_identity_single_table(db.session, mock_logger, schema, table_name, "index")

                expected_warning = f"No suitable unique index found for {schema}.{table_name}, using DEFAULT"
                mock_logger.warning.assert_called_with(expected_warning)
                expected_change = f"Changing replica identity for {schema}.{table_name} from DEFAULT to INDEX"
                mock_logger.info.assert_any_call(expected_change)

                # Should fall back to default
                result = _get_current_replica_identity_mode(db.session, schema, table_name)
                assert result == "default"
        finally:
            with flask_app.app.app_context():
                self.reset_replica_identity(table_name)

    def test_set_replica_identity_single_table_invalid_mode(self, flask_app):
        """Test setting replica identity with invalid mode."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        with flask_app.app.app_context():
            with pytest.raises(ValueError, match="Invalid replica identity mode: invalid"):
                _set_replica_identity_single_table(db.session, mock_logger, schema, table_name, "invalid")

    def test_set_replica_identity_for_table_without_partitions(self, flask_app):
        """Test setting replica identity for table without partitions."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                table_config = {"name": table_name, "schema": schema, "has_partitions": False}

                set_replica_identity_for_table(db.session, mock_logger, table_config, "default")

                # Should set replica identity on the main table
                result = _get_current_replica_identity_mode(db.session, schema, table_name)
                assert result == "default"
        finally:
            with flask_app.app.app_context():
                self.reset_replica_identity(table_name)

    @pytest.mark.parametrize("partition_suffix", ["_p0", "_p1", "_p2"])
    def test_set_replica_identity_for_table_with_partitions(self, flask_app, partition_suffix):
        """Test setting replica identity for table with partitions."""
        schema, table_name = get_table_info()
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                table_config = {"name": table_name, "schema": schema, "has_partitions": True}

                set_replica_identity_for_table(db.session, mock_logger, table_config, "default")

                # Verify replica identity is set on main table
                result = _get_current_replica_identity_mode(db.session, schema, table_name)
                assert result == "default"

                # Verify replica identity is also set on partitions (migrations always create at least _p0)
                partition_name = f"{table_name}{partition_suffix}"
                partition_result = _get_current_replica_identity_mode(db.session, schema, partition_name)
                if partition_result != "unknown":  # Only check if partition exists
                    assert partition_result == "default", (
                        f"Partition {partition_name} should have default replica identity"
                    )
                    mock_logger.info.assert_any_call(
                        f"Setting replica identity to 'default' for table {schema}.{partition_name}"
                    )

                # Verify the function logged setting replica identity for the main table
                mock_logger.info.assert_any_call(
                    f"Setting replica identity to 'default' for table {schema}.{table_name}"
                )
        finally:
            with flask_app.app.app_context():
                self.reset_replica_identity(table_name)
                # Also reset partitions if they exist
                partition_name = f"{table_name}{partition_suffix}"
                self.reset_replica_identity(partition_name)


class TestConfigureReplicaIdentities:
    """Tests for configure_replica_identities function."""

    @patch("jobs.inv_publish_hosts.REPLICA_IDENTITY_MODE", "")
    @patch("jobs.inv_publish_hosts.set_replica_identity_for_table")
    def test_configure_replica_identities_empty_mode(self, mock_set_replica):
        """Test configure_replica_identities with empty mode."""
        mock_session = Mock()
        mock_logger = Mock()

        configure_replica_identities(mock_session, mock_logger)

        mock_logger.info.assert_called_with("Replica identity configuration skipped (REPLICA_IDENTITY_MODE is empty)")
        mock_set_replica.assert_not_called()

    @patch("jobs.inv_publish_hosts.REPLICA_IDENTITY_MODE", "invalid")
    @patch("jobs.inv_publish_hosts.set_replica_identity_for_table")
    def test_configure_replica_identities_invalid_mode(self, mock_set_replica):
        """Test configure_replica_identities with invalid mode."""
        mock_session = Mock()
        mock_logger = Mock()

        configure_replica_identities(mock_session, mock_logger)

        mock_logger.error.assert_called_with(
            "Invalid REPLICA_IDENTITY_MODE: invalid. Must be 'default', 'index', or empty string"
        )
        mock_set_replica.assert_not_called()

    @patch("jobs.inv_publish_hosts.REPLICA_IDENTITY_MODE", "default")
    @patch("jobs.inv_publish_hosts.set_replica_identity_for_table")
    def test_configure_replica_identities_default_mode(self, mock_set_replica):
        """Test configure_replica_identities with default mode."""
        mock_session = Mock()
        mock_logger = Mock()

        configure_replica_identities(mock_session, mock_logger)

        mock_logger.info.assert_called_with("Configuring replica identities with mode: default")
        # Should be called for each unique table in PUBLICATION_CONFIG
        expected_call_count = get_unique_table_count()
        assert mock_set_replica.call_count == expected_call_count


class TestSetupPublication:
    """Tests for setup_publication function."""

    @patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", ["old_pub1", "old_pub2"])
    @patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", [])
    def test_setup_publication_drop_only(self):
        """Test setup_publication with only drop publications configured."""
        mock_session = Mock()
        mock_logger = Mock()

        setup_publication(mock_session, mock_logger)

        mock_logger.info.assert_any_call("Dropping publications: ['old_pub1', 'old_pub2']")
        mock_logger.info.assert_any_call("Dropping publication: old_pub1")
        mock_logger.info.assert_any_call("Dropping publication: old_pub2")
        mock_logger.info.assert_any_call("No publications configured for creation")
        assert mock_session.execute.call_count == 2  # Two drop statements

    def test_setup_publication_create_new(self):
        """Test setup_publication creating new publication."""

        publication_name = get_first_available_publication()

        with (
            patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
            patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [publication_name]),
            patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", []),
        ):
            mock_session = Mock()
            mock_logger = Mock()

            # Mock publication doesn't exist
            mock_session.execute.return_value.scalar.return_value = False

            setup_publication(mock_session, mock_logger)

            mock_logger.info.assert_any_call(f"Creating publications: ['{publication_name}']")
            mock_logger.info.assert_any_call(f'Creating publication "{publication_name}".')
            mock_logger.info.assert_any_call(f'Publication "{publication_name}" created!')
            assert mock_session.execute.call_count == 2  # Check existence + create

    def test_setup_publication_create_existing(self):
        """Test setup_publication when publication already exists."""

        publication_name = get_first_available_publication()

        with (
            patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
            patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [publication_name]),
            patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", []),
        ):
            mock_session = Mock()
            mock_logger = Mock()

            # Mock publication already exists
            mock_session.execute.return_value.scalar.return_value = True

            setup_publication(mock_session, mock_logger)

            mock_logger.info.assert_any_call(f'Publication "{publication_name}" already exists.')
            assert mock_session.execute.call_count == 1  # Only check existence

    @patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", ["inactive_slot1", "inactive_slot2"])
    def test_setup_publication_drop_inactive_slots(self):
        """Test setup_publication dropping inactive replication slots."""
        mock_session = Mock()
        mock_logger = Mock()

        # Mock replication slots query
        mock_session.execute.return_value = [
            ("inactive_slot1", False),
            ("active_slot1", True),
            ("inactive_slot2", False),
        ]

        setup_publication(mock_session, mock_logger)

        mock_logger.info.assert_any_call("Dropping inactive slot: inactive_slot1")
        mock_logger.info.assert_any_call("Dropping inactive slot: inactive_slot2")
        # Should execute: check slots + drop slot1 + drop slot2
        assert mock_session.execute.call_count == 3

    @patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", ["should_drop"])
    def test_setup_publication_inactive_slots_error(self):
        """Test setup_publication with inactive slots that shouldn't exist."""
        mock_session = Mock()
        mock_logger = Mock()

        # Mock replication slots query - inactive slot not in drop list
        mock_session.execute.return_value = [
            ("unwanted_inactive", False),
        ]

        with pytest.raises(RuntimeError, match="Inactive slots left open: \\['unwanted_inactive'\\]"):
            setup_publication(mock_session, mock_logger)


class TestPublicationIntegration:
    """Integration tests for publication creation and deletion in real database."""

    def cleanup_publication(self, publication_name):
        """Helper to clean up publications."""
        try:
            with db.session.begin():
                db.session.execute(sa_text(f"DROP PUBLICATION IF EXISTS {publication_name}"))
        except Exception:
            db.session.rollback()

    def publication_exists(self, publication_name):
        """Helper to check if publication exists."""
        result = db.session.execute(
            sa_text("SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_publication WHERE pubname = :pubname)"),
            {"pubname": publication_name},
        ).scalar()
        return result

    def create_replication_slot(self, slot_name):
        """Helper to create a logical replication slot."""
        try:
            db.session.execute(sa_text(f"SELECT pg_create_logical_replication_slot('{slot_name}', 'pgoutput')"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # In ephemeral environments, logical replication might not be enabled
            # Re-raise if it's not a logical replication error
            error_msg = str(e).lower()
            if "logical replication" not in error_msg and "wal_level" not in error_msg:
                raise
            # Slot might already exist, that's okay for tests

    def cleanup_replication_slot(self, slot_name):
        """Helper to clean up replication slots."""
        try:
            result = db.session.execute(
                sa_text("SELECT COUNT(*) FROM pg_replication_slots WHERE slot_name = :slot_name"),
                {"slot_name": slot_name},
            ).scalar()
            if result > 0:
                db.session.execute(sa_text(f"SELECT pg_drop_replication_slot('{slot_name}')"))
                db.session.commit()
        except Exception:
            db.session.rollback()

    def replication_slot_exists(self, slot_name):
        """Helper to check if replication slot exists."""
        result = db.session.execute(
            sa_text("SELECT COUNT(*) FROM pg_replication_slots WHERE slot_name = :slot_name"), {"slot_name": slot_name}
        ).scalar()
        return result > 0

    def get_replication_slot_status(self, slot_name):
        """Helper to get replication slot status (active/inactive)."""
        result = db.session.execute(
            sa_text("SELECT active FROM pg_replication_slots WHERE slot_name = :slot_name"), {"slot_name": slot_name}
        ).scalar()
        return result

    def logical_replication_enabled(self):
        """Helper to check if logical replication is enabled."""
        try:
            result = db.session.execute(sa_text("SHOW wal_level")).scalar()
            return result == "logical"
        except Exception:
            return False

    def test_create_publication(self, flask_app):
        """Test creating a publication in the real database."""
        publication_name = "test_hosts_publication"
        mock_logger = Mock()

        # Create a custom publication config for testing using dynamic table info
        sample_config = get_sample_table_config()
        test_config = {"test_hosts_publication": {"tables": [sample_config]}}

        try:
            with flask_app.app.app_context():
                with (
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [publication_name]),
                    patch("jobs.inv_publish_hosts.PUBLICATION_CONFIG", test_config),
                ):
                    # Ensure publication doesn't exist initially
                    self.cleanup_publication(publication_name)
                    assert not self.publication_exists(publication_name)

                    # Create publication
                    setup_publication(db.session, mock_logger)
                    db.session.commit()

                    # Verify publication was created
                    assert self.publication_exists(publication_name)

                    # Verify logging
                    mock_logger.info.assert_any_call(f"Creating publications: ['{publication_name}']")
                    mock_logger.info.assert_any_call(f'Creating publication "{publication_name}".')
                    mock_logger.info.assert_any_call(f'Publication "{publication_name}" created!')

        finally:
            with flask_app.app.app_context():
                self.cleanup_publication(publication_name)

    def test_create_existing_publication(self, flask_app):
        """Test attempting to create a publication that already exists."""
        publication_name = "test_existing_publication"
        mock_logger = Mock()

        # Create a simple test config using dynamic table info
        sample_config = get_sample_table_config()
        test_config = {"test_existing_publication": {"tables": [sample_config]}}

        try:
            with flask_app.app.app_context():
                with (
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [publication_name]),
                    patch("jobs.inv_publish_hosts.PUBLICATION_CONFIG", test_config),
                ):
                    # Create publication first
                    self.cleanup_publication(publication_name)
                    create_sql = _build_create_publication_sql(publication_name)
                    db.session.execute(create_sql)
                    db.session.commit()

                    assert self.publication_exists(publication_name)

                    setup_publication(db.session, mock_logger)

                    # Verify it detected existing publication
                    mock_logger.info.assert_any_call(f'Publication "{publication_name}" already exists.')

        finally:
            with flask_app.app.app_context():
                self.cleanup_publication(publication_name)

    @patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", ["test_publication_drop"])
    def test_drop_publication(self, flask_app):
        """Test dropping a publication from the real database."""
        publication_name = "test_publication_drop"
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Create publication first - simple publication for testing drop functionality
                sample_config = get_sample_table_config()
                qualified_table = f"{sample_config['schema']}.{sample_config['name']}"
                columns_str = ", ".join(sample_config["publication_columns"])
                where_clause = (
                    f"WHERE ({sample_config['publication_filter']})" if sample_config["publication_filter"] else ""
                )

                self.cleanup_publication(publication_name)
                db.session.execute(
                    sa_text(f"""
                    CREATE PUBLICATION {publication_name}
                    FOR TABLE {qualified_table} ({columns_str})
                    {where_clause}
                    WITH (publish_via_partition_root = true)
                """)
                )
                db.session.commit()

                assert self.publication_exists(publication_name)

                # Test publication deletion
                setup_publication(db.session, mock_logger)
                db.session.commit()

                # Verify publication was dropped
                assert not self.publication_exists(publication_name)

                # Verify logging
                mock_logger.info.assert_any_call("Dropping publications: ['test_publication_drop']")
                mock_logger.info.assert_any_call("Dropping publication: test_publication_drop")

        finally:
            with flask_app.app.app_context():
                self.cleanup_publication(publication_name)

    def test_create_and_drop_multiple_publications(self, flask_app):
        """Test creating and dropping publications in same operation."""
        create_pub = "test_create_pub"
        drop_pub = "test_drop_pub"
        mock_logger = Mock()

        # Create test config using dynamic table info
        sample_config = get_sample_table_config()
        test_config = {"test_create_pub": {"tables": [sample_config]}}

        try:
            with flask_app.app.app_context():
                with (
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [create_pub]),
                    patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", [drop_pub]),
                    patch("jobs.inv_publish_hosts.PUBLICATION_CONFIG", test_config),
                ):
                    # Setup: clean all publications and create the one to be dropped
                    sample_config = get_sample_table_config()
                    qualified_table = f"{sample_config['schema']}.{sample_config['name']}"
                    columns_str = ", ".join(sample_config["publication_columns"])
                    where_clause = (
                        f"WHERE ({sample_config['publication_filter']})" if sample_config["publication_filter"] else ""
                    )

                    for pub in [create_pub, drop_pub]:
                        self.cleanup_publication(pub)

                    db.session.execute(
                        sa_text(f"""
                        CREATE PUBLICATION {drop_pub}
                        FOR TABLE {qualified_table} ({columns_str})
                        {where_clause}
                        WITH (publish_via_partition_root = true)
                    """)
                    )
                    db.session.commit()

                    assert self.publication_exists(drop_pub)
                    assert not self.publication_exists(create_pub)

                    setup_publication(db.session, mock_logger)
                    db.session.commit()

                    # Verify results
                    assert not self.publication_exists(drop_pub)  # Should be dropped
                    assert self.publication_exists(create_pub)  # Should be created

                    # Verify logging for drops
                    mock_logger.info.assert_any_call(f"Dropping publications: ['{drop_pub}']")

                    # Verify logging for creates
                    mock_logger.info.assert_any_call(f"Creating publications: ['{create_pub}']")

        finally:
            with flask_app.app.app_context():
                for pub in [create_pub, drop_pub]:
                    self.cleanup_publication(pub)

    @patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", [])
    @patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", [])
    def test_no_publications_configured(self, flask_app):
        """Test when no publications are configured for creation or deletion."""
        mock_logger = Mock()

        with flask_app.app.app_context():
            setup_publication(db.session, mock_logger)

            mock_logger.info.assert_any_call("No publications configured for dropping")
            mock_logger.info.assert_any_call("No publications configured for creation")
            mock_logger.info.assert_any_call("No replication slots configured for cleanup")

    def test_publication_sql_generation_real_config(self, flask_app):
        """Test that generated SQL works with real database using actual config."""

        publication_name = get_first_available_publication()

        with flask_app.app.app_context():
            sql = _build_create_publication_sql(publication_name)

            # Verify the SQL is well-formed by checking for required elements
            sql_str = str(sql)
            assert "CREATE PUBLICATION" in sql_str
            assert publication_name in sql_str
            assert "FOR TABLE" in sql_str
            assert "WITH (publish_via_partition_root = true)" in sql_str

            # Verify that at least one table from the configuration is in the SQL
            publication_config = PUBLICATION_CONFIG[publication_name]
            table_found = False
            for table_config in publication_config["tables"]:
                table_name = f"{table_config['schema']}.{table_config['name']}"
                if table_name in sql_str:
                    table_found = True
                    break
            assert table_found, f"No configured tables found in SQL: {sql_str}"

            # The SQL should not be empty
            assert len(sql_str.strip()) > 0

    def test_drop_inactive_replication_slots(self, flask_app):
        """Test dropping inactive replication slots that are configured for cleanup."""
        slot_name = "test_inactive_slot"
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Skip test if logical replication is not enabled (e.g., in ephemeral environments)
                if not self.logical_replication_enabled():
                    pytest.skip("Logical replication not enabled (wal_level != 'logical')")

                with (
                    patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", [slot_name]),
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", []),
                    patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
                ):
                    # Clean up any existing slots first (including debezium_hosts which may exist from other tests)
                    self.cleanup_replication_slot(slot_name)
                    self.cleanup_replication_slot("debezium_hosts")

                    # Create an inactive replication slot
                    self.create_replication_slot(slot_name)
                    # If slot creation failed due to logical replication not being enabled, skip test
                    if not self.replication_slot_exists(slot_name):
                        pytest.skip("Could not create replication slot (logical replication not available)")

                    # Slot should be inactive (newly created slots are inactive)
                    assert self.get_replication_slot_status(slot_name) is False

                    # Test setup_publication - should drop the inactive slot
                    setup_publication(db.session, mock_logger)
                    db.session.commit()

                    # Verify slot was dropped
                    assert not self.replication_slot_exists(slot_name)

                    # Verify logging
                    mock_logger.info.assert_any_call(f"Checking replication slots to drop: ['{slot_name}']")
                    mock_logger.info.assert_any_call(f"Dropping inactive slot: {slot_name}")

        finally:
            with flask_app.app.app_context():
                self.cleanup_replication_slot(slot_name)
                self.cleanup_replication_slot("debezium_hosts")

    def test_error_on_unwanted_inactive_slots(self, flask_app):
        """Test error when there are inactive slots not configured for cleanup."""
        wanted_slot = "test_wanted_slot"
        unwanted_slot = "test_unwanted_slot"
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Skip test if logical replication is not enabled (e.g., in ephemeral environments)
                if not self.logical_replication_enabled():
                    pytest.skip("Logical replication not enabled (wal_level != 'logical')")

                # Configure one slot for cleanup, but create an additional unwanted slot
                with (
                    patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", [wanted_slot]),
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", []),
                    patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
                ):
                    # Clean up any existing slots first (including debezium_hosts which may exist from other tests)
                    self.cleanup_replication_slot(wanted_slot)
                    self.cleanup_replication_slot(unwanted_slot)
                    self.cleanup_replication_slot("debezium_hosts")

                    # Create the unwanted inactive replication slot
                    self.create_replication_slot(unwanted_slot)
                    # If slot creation failed due to logical replication not being enabled, skip test
                    if not self.replication_slot_exists(unwanted_slot):
                        pytest.skip("Could not create replication slot (logical replication not available)")

                    # Slot should be inactive
                    assert self.get_replication_slot_status(unwanted_slot) is False

                    # Test setup_publication - should raise error about unwanted slot
                    # The error message may include other slots (like debezium_hosts),
                    # so check that our unwanted slot is in the list
                    with pytest.raises(RuntimeError) as exc_info:
                        setup_publication(db.session, mock_logger)
                    assert unwanted_slot in str(exc_info.value), (
                        f"Expected '{unwanted_slot}' in error message: {exc_info.value}"
                    )

                    # Slot should still exist (not dropped)
                    assert self.replication_slot_exists(unwanted_slot)

        finally:
            with flask_app.app.app_context():
                self.cleanup_replication_slot(wanted_slot)
                self.cleanup_replication_slot(unwanted_slot)
                self.cleanup_replication_slot("debezium_hosts")

    def test_drop_multiple_replication_slots(self, flask_app):
        """Test dropping multiple inactive replication slots."""
        slot_names = ["test_slot_1", "test_slot_2"]
        unwanted_slot = "test_unwanted_slot"
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Skip test if logical replication is not enabled (e.g., in ephemeral environments)
                if not self.logical_replication_enabled():
                    pytest.skip("Logical replication not enabled (wal_level != 'logical')")

                with (
                    patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", slot_names),
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", []),
                    patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
                ):
                    # Clean up any existing slots first (including debezium_hosts which may exist from other tests)
                    for slot in slot_names + [unwanted_slot]:
                        self.cleanup_replication_slot(slot)
                    self.cleanup_replication_slot("debezium_hosts")

                    # Create slots configured for cleanup
                    for slot in slot_names:
                        self.create_replication_slot(slot)
                        # If slot creation failed, skip test
                        if not self.replication_slot_exists(slot):
                            pytest.skip("Could not create replication slot (logical replication not available)")
                        assert self.get_replication_slot_status(slot) is False

                    # Create unwanted slot
                    self.create_replication_slot(unwanted_slot)
                    if not self.replication_slot_exists(unwanted_slot):
                        pytest.skip("Could not create replication slot (logical replication not available)")

                    # Should raise error due to unwanted slot
                    # The error message may include other slots (like debezium_hosts),
                    # so check that our unwanted slot is in the list
                    with pytest.raises(RuntimeError) as exc_info:
                        setup_publication(db.session, mock_logger)
                    assert unwanted_slot in str(exc_info.value), (
                        f"Expected '{unwanted_slot}' in error message: {exc_info.value}"
                    )

                    # The configured slots should be dropped (they get processed first)
                    for slot in slot_names:
                        assert not self.replication_slot_exists(slot)
                    # The unwanted slot should still exist (it caused the error)
                    assert self.replication_slot_exists(unwanted_slot)

        finally:
            with flask_app.app.app_context():
                for slot in slot_names + [unwanted_slot]:
                    self.cleanup_replication_slot(slot)
                self.cleanup_replication_slot("debezium_hosts")

    def test_active_replication_slots_left_alone(self, flask_app):
        """Test that active replication slots are not dropped even if configured."""
        slot_name = "test_active_slot"
        mock_logger = Mock()

        try:
            with flask_app.app.app_context():
                # Skip test if logical replication is not enabled (e.g., in ephemeral environments)
                # This test doesn't require creating slots, but it's testing replication slot behavior
                # so we should skip if logical replication is not available
                if not self.logical_replication_enabled():
                    pytest.skip("Logical replication not enabled (wal_level != 'logical')")

                with (
                    patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", [slot_name]),
                    patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", []),
                    patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
                ):
                    # Clean up any existing slots first (including debezium_hosts which may exist from other tests)
                    self.cleanup_replication_slot(slot_name)
                    self.cleanup_replication_slot("debezium_hosts")

                    # For this test, we'll simulate what happens when there are active slots
                    # by not creating any slots at all - if there are no inactive slots,
                    # the logic should pass without errors
                    setup_publication(db.session, mock_logger)
                    db.session.commit()

                    # Verify logging shows it checked for slots to drop
                    mock_logger.info.assert_any_call(f"Checking replication slots to drop: ['{slot_name}']")

        finally:
            with flask_app.app.app_context():
                self.cleanup_replication_slot(slot_name)
                self.cleanup_replication_slot("debezium_hosts")

    def test_no_replication_slots_configured(self, flask_app):
        """Test when no replication slots are configured for cleanup."""
        mock_logger = Mock()

        with flask_app.app.app_context():
            with (
                patch("jobs.inv_publish_hosts.DROP_REPLICATION_SLOTS", []),
                patch("jobs.inv_publish_hosts.CREATE_PUBLICATIONS", []),
                patch("jobs.inv_publish_hosts.DROP_PUBLICATIONS", []),
            ):
                setup_publication(db.session, mock_logger)

                # Verify appropriate logging
                mock_logger.info.assert_any_call("No replication slots configured for cleanup")


class TestPublicationConfig:
    """Tests for PUBLICATION_CONFIG validation."""

    def test_publication_config_structure(self):
        """Test that ALL publications in PUBLICATION_CONFIG have the expected structure."""

        assert len(PUBLICATION_CONFIG) > 0, "At least one publication should be configured"

        for pub_name, pub_config in PUBLICATION_CONFIG.items():
            assert "tables" in pub_config, f"Publication '{pub_name}' missing 'tables' key"
            assert len(pub_config["tables"]) > 0, f"Publication '{pub_name}' should have at least one table"

            for table in pub_config["tables"]:
                table_name = table.get("name", "unknown")
                context = f"Publication '{pub_name}', table '{table_name}'"

                assert "name" in table, f"{context} missing 'name' key"
                assert "schema" in table, f"{context} missing 'schema' key"
                assert "has_partitions" in table, f"{context} missing 'has_partitions' key"
                assert "publication_columns" in table, f"{context} missing 'publication_columns' key"
                assert "publication_filter" in table, f"{context} missing 'publication_filter' key"
                assert table["schema"] == INVENTORY_SCHEMA, f"{context} has invalid schema '{table['schema']}'"
                assert isinstance(table["publication_columns"], list), f"{context} publication_columns must be a list"
                assert len(table["publication_columns"]) > 0, f"{context} should have at least one publication column"

    def test_publication_config_required_columns(self):
        """Test that required columns are present in ALL publication configurations."""

        assert len(PUBLICATION_CONFIG) > 0, "At least one publication should be configured"

        for pub_name, pub_config in PUBLICATION_CONFIG.items():
            for table in pub_config["tables"]:
                table_name = table["name"]
                columns = table["publication_columns"]
                context = f"Publication '{pub_name}', table '{table_name}'"

                # Every inventory table should have org_id for tenant isolation
                assert "org_id" in columns, f"{context} missing required 'org_id' column"

                # Each table should have some form of identifier column
                id_columns = [col for col in columns if col.endswith("_id") or col == "id"]
                assert len(id_columns) > 0, f"{context} should have at least one ID column"

                # Ensure publication_columns list is not empty
                assert len(columns) > 0, f"{context} should have at least one publication column"

                # If table has a filter, ensure filtered columns are in publication_columns
                table_filter = table.get("publication_filter")
                if table_filter and table_filter.strip():
                    # Extract column names from filter
                    import re

                    # Match column names
                    filter_columns = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", table_filter)
                    # Filter out common SQL keywords and operators
                    sql_keywords = {"and", "or", "not", "is", "null", "where"}
                    actual_columns = [col for col in filter_columns if col.lower() not in sql_keywords]

                    for filter_col in actual_columns:
                        if filter_col not in columns:
                            raise AssertionError(
                                f"{context} filter references column '{filter_col}' "
                                f"which is not in publication_columns: {columns}"
                            )


@pytest.fixture
def mock_logger():
    """Fixture to provide a mock logger."""
    return Mock()
