# CLAUDE.md

## Project

Red Hat Insights Host Based Inventory (HBI) — Flask REST API managing system inventory data, backed by PostgreSQL (partitioned tables) and Kafka.

## Key Commands

- `make style` — run before committing (pre-commit / ruff)
- `make hbi-help` — list all dev workflow targets (defined in `mk/private.mk`)
- `pipenv run pytest --cov=.` — run tests with coverage
- `podman compose -f dev.yml up -d` / `down` — start/stop containerized services
- `make upgrade_db` — run Alembic migrations
- `make migrate_db message="..."` — generate a new migration
- `git submodule update --init --recursive` — initialize submodules (e.g., `librdkafka`)

## Conventions

- Always `unset PIPENV_PIPFILE` before pipenv commands — two Pipenv environments exist (dev and IQE in `iqe-host-inventory-plugin/`)
- Auth uses `x-rh-identity` header (Base64-encoded JSON with org_id) — org_id isolates tenant data
- DB schema is `hbi.*` with partitioned tables
- The `hbi-web` container auto-reloads on code changes — no manual restart needed

## Structure

- `app/` — Flask app, models, auth, config
- `api/` — REST endpoints (hosts, groups, system profiles, staleness)
- `lib/` — business logic and repository patterns
- `jobs/` — background jobs (host reaper)
- `migrations/` — Alembic migrations
- `mk/private.mk` — dev workflow and Claude Code make targets
- `.claude/` — hooks and slash commands
