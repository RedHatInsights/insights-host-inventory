# CLAUDE.md

## Project

Red Hat Insights Host Based Inventory (HBI) — Flask REST API managing system inventory data, backed by PostgreSQL (partitioned tables) and Kafka.

## Key Commands

- `make style` — run before committing (pre-commit / ruff)
- `make hbi-help` — list all dev workflow targets (defined in `mk/private.mk`)
- `uv run pytest --cov=.` — run tests with coverage
- `podman compose -f dev.yml up -d` / `down` — start/stop containerized services
- `make upgrade_db` — run Alembic migrations
- `make migrate_db message="..."` — generate a new migration
- `git submodule update --init --recursive` — initialize submodules (e.g., `librdkafka`)

## Conventions

- Main app: `uv sync --frozen` at repo root. IQE: `uv --project iqe-host-inventory-plugin sync --frozen` (see `docs/IQE.md`). Both use uv with separate venvs and lockfiles.
- Set a minimum `uv` CLI version via `[tool.uv] required-version` in `pyproject.toml` (for Dependabot/MintMaker compatibility).
- Pin the exact `uv` version used in hermetic builds via `uv-build-version` (must satisfy `required-version`).
- Dockerfiles install uv via `COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION}` with `ARG UV_VERSION` defaulted to the same pin as `uv-build-version` (CI checks they match). Override with `--build-arg UV_VERSION=…` when needed. Runtime images do not include `pip`; use `uv`.
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
