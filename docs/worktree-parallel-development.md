# Worktree-Based Parallel Development

Run multiple HBI branches simultaneously, each with its own fully isolated application stack (PostgreSQL, Kafka, Redis, Unleash, etc.), virtual environments, and database storage.

## When to use this

- **Agentic development:** Multiple AI agents working on independent branches at the same time, each needing their own services.
- **Parallel feature work:** You're working on two features that each need a running stack with test data, and switching between them by tearing down / rebuilding is too slow.
- **Code review with a live stack:** You want to spin up a reviewer's branch alongside your own to compare behavior, run tests, or inspect data side-by-side.
- **Reproducing bugs on specific branches:** Stand up an older branch's stack without disrupting your current work.

If you only work on one branch at a time, the standard `podman compose -f dev.yml up -d` workflow is all you need — this script adds no value for single-branch development.

## How it works

Each worktree gets a **slot** (1–8). All host ports are offset by `slot * 100` from the defaults, so there are no collisions. The main worktree keeps default ports and is completely unaffected.

| Resource | Isolation mechanism |
|----------|-------------------|
| Containers | Unique `COMPOSE_PROJECT_NAME` per worktree → separate Podman network |
| Ports | Slot-based offset (e.g., slot 1: DB on 5532, Web on 8180) |
| Database storage | Separate `~/.pg_data_<name>` directory per worktree |
| Python venv (main) | `uv sync --frozen` creates `.venv/` in each worktree directory |
| Python venv (IQE) | `uv --project iqe-host-inventory-plugin sync --frozen` creates `iqe-host-inventory-plugin/.venv/` in each worktree |
| Kafka, Redis, etc. | Each stack has its own isolated instances on a separate Podman network |

## Quick start

```bash
# Create a worktree with full stack (DB, Kafka, Redis, etc.)
./scripts/worktree.sh create my-feature

# Create without IQE venv (faster, skip if you don't need to run IQE tests locally)
./scripts/worktree.sh create --no-iqe my-feature

# List all worktrees and their status
./scripts/worktree.sh list

# Stop the stack (removes DB data by default)
./scripts/worktree.sh down my-feature

# Stop the stack but keep DB data
./scripts/worktree.sh down my-feature --keep-db

# Start an existing worktree's stack
./scripts/worktree.sh up my-feature

# Tear down and restart with a fresh database
./scripts/worktree.sh up my-feature --clean

# Completely remove a worktree (stack, venvs, DB data, git worktree, branch)
./scripts/worktree.sh destroy my-feature
```

All commands can also be run from inside a worktree directory without specifying the name:

```bash
cd worktrees/my-feature
./scripts/worktree.sh up
./scripts/worktree.sh down
```

## What `create` does

1. Creates a git worktree at `worktrees/<name>/` on a new branch
2. Initializes submodules
3. Generates a `.env` file with computed port offsets and app configuration
4. Installs main and IQE virtual environments (in parallel)
5. Starts the Podman Compose stack (11 services)
6. Waits for the database to become healthy
7. Runs Alembic migrations
8. Prints activation commands for both venvs

If any step fails, it cleans up everything it created (DB data, venvs, git worktree).

## Port allocation

| Service | Default (main) | Slot 1 | Slot 2 | Slot 3 |
|---------|---------------|--------|--------|--------|
| PostgreSQL | 5432 | 5532 | 5632 | 5732 |
| HBI Web API | 8080 | 8180 | 8280 | 8380 |
| Kafka (external) | 9092 | 9192 | 9292 | 9392 |
| Kafka (internal) | 29092 | 29192 | 29292 | 29392 |
| Redis | 6379 | 6479 | 6579 | 6679 |
| Unleash | 4242 | 4342 | 4442 | 4542 |

Up to 8 worktree slots are available (135 total ports across all 9 stacks, verified collision-free).

## Activating the environment

After creating or starting a worktree, activate the appropriate venv:

```bash
# Main app/test environment
cd worktrees/my-feature && source .venv/bin/activate

# IQE test environment
cd worktrees/my-feature && source iqe-host-inventory-plugin/.venv/bin/activate
```

## Environment variables

Each worktree's `.env` is auto-generated with the correct ports for all services. This includes variables consumed by the app and tests when running on the host:

- `INVENTORY_DB_PORT` — PostgreSQL port
- `KAFKA_BOOTSTRAP_SERVERS` — Kafka broker address (e.g., `localhost:29192`)
- `CACHE_PORT` — Redis port
- `UNLEASH_URL` — Unleash API URL with correct port
- `PROMETHEUS_PUSHGATEWAY` — Prometheus gateway address
- `EXPORT_SERVICE_ENDPOINT` — Export service address

Container-internal connections (services talking to each other inside the Podman network) are unaffected — they use service names on standard ports.

## Resource usage

Each worktree runs a full 11-service Podman Compose stack. The typical use case is 2–3 concurrent worktrees; running all 8 slots is possible but resource-intensive.

Destroying a worktree cleans up everything: containers, Podman network, DB data directory, both virtual environments (main and IQE), the git worktree, and the branch (if fully merged).
