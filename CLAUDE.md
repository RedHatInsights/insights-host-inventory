# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Database Operations
- `make upgrade_db` - Run database migrations to upgrade to the latest schema
- `make migrate_db message="Description"` - Generate a new database migration

### Testing and Quality
- `pytest --cov=.` - Run all tests with coverage
- `pytest tests/test_api_auth.py` - Run tests in a specific file
- `pytest tests/test_api_auth.py::test_validate_valid_identity` - Run a specific test
- `make style` - Run pre-commit hooks for code formatting

### Local Development Services
- `make run_inv_export_service` - Start the export service for data exports
- `make run_inv_mq_service_test_producer NUM_HOSTS=800` - Generate test host data

### Containerized Development Environment
- `docker compose -f dev.yml up -d` - Start all services (PostgreSQL, Kafka, Redis, etc.) with auto-reloading
- `docker compose -f dev.yml down` - Stop all services

**Auto-Reloading Web Service**: The `hbi-web` container includes automatic code reloading for development:
- **File Watcher**: `dev_server.py` monitors Python, YAML, and JSON files for changes
- **Smart Restart**: Automatically restarts Flask when code changes are detected
- **Debouncing**: Prevents rapid restarts during bulk file operations
- **Clean Logs**: Provides clear feedback when files change and server restarts
- **Volume Mount**: Local repository is mounted at `/opt/app-root/src` for real-time file sync

This eliminates the need to manually restart containers during development. Simply save your files and the web service will automatically reload.

### Environment Setup

#### Main Development Environment
- `pipenv install --dev` - Install dependencies
- `pipenv shell` - Activate virtual environment
- `docker compose -f dev.yml up -d` - Start dependent services (PostgreSQL, Kafka, etc.)

#### IQE Test Environment
The IQE test suite is maintained in the `iqe-host-inventory-plugin/` subdirectory and uses a separate Pipenv environment with dependencies from Red Hat Nexus.

See `docs/IQE.md` for complete setup and usage instructions.

### Schema Management
- `make update-schema` - Update system profile schema from inventory-schemas repo

## Architecture Overview

### Core Components
This is the Red Hat Insights Host Based Inventory (HBI) service, which manages system inventory data for Red Hat's cloud platform.

**Application Structure:**
- `app/` - Main Flask application with models, auth, configuration
- `api/` - REST API endpoints for hosts, groups, system profiles, staleness
- `lib/` - Core business logic and repository patterns
- `jobs/` - Background job processing
- `migrations/` - Alembic database migrations
- `utils/` - Utility scripts and tools

**Key Services:**
- **Web Service** (`run.py`): Flask REST API for inventory operations
- **MQ Service** (`inv_mq_service.py`): Kafka consumer for host updates
- **Export Service** (`inv_export_service.py`): Data export functionality
- **Reaper** (`jobs/host_reaper.py`): Cleanup of stale hosts

### Data Flow
1. Host data arrives via Kafka messages (processed by MQ service)
2. Data is validated and stored in PostgreSQL with partitioned tables
3. REST API provides access to host data with RBAC and filtering
4. Export service handles bulk data extraction requests
5. Background jobs handle staleness tracking and cleanup

### Key Technologies
- **Flask** with **Gunicorn** for web service
- **PostgreSQL** with partitioned tables for scalability
- **Kafka** for event-driven host updates
- **Redis** for caching (via Clowder)
- **SQLAlchemy** with **Alembic** for database ORM and migrations
- **Prometheus** for metrics and monitoring

### Authentication & Authorization
- Uses Red Hat Identity headers (`x-rh-identity`) for authentication
- RBAC (Role-Based Access Control) for authorization
- Org ID isolation ensures tenant data separation

### Testing Strategy
- Unit tests cover business logic and API endpoints

### Code Quality
- Run `make style` to ensure code is formartted
