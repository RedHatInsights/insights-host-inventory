# /hbi-install-hil - Interactive Human-in-the-Loop HBI Setup

Interactive setup that asks the user preferences before configuring the environment.

## Instructions

1. First, orient yourself by reading `CLAUDE.md`.

2. Use `AskUserQuestion` to ask the user these setup preferences:

   **Question 1 - Database**:
   - "How should the PostgreSQL database be handled?"
   - Options:
     - "Fresh start" (description: "Remove ~/.pg_data and start with a clean database")
     - "Keep existing" (description: "Keep existing data in ~/.pg_data if present")
     - "Skip" (description: "Do not start or configure the database")

   **Question 2 - Dependencies**:
   - "How should Python dependencies be handled?"
   - Options:
     - "Full install" (description: "Run pipenv install --dev to install all dependencies")
     - "Skip" (description: "Skip dependency installation, assume already installed")

   **Question 3 - Podman services**:
   - "Which Podman services should be started?"
   - Options:
     - "All services" (description: "Start all services defined in dev.yml (db, kafka, unleash, minio, hbi-web, hbi-mq, hbi-mq-apps, etc.)")
     - "Minimal" (description: "Start only db and kafka containers")
     - "Skip" (description: "Do not start any Podman services")

   **Question 4 - Environment check**:
   - "Run environment prerequisite checks first?"
   - Options:
     - "Yes (Recommended)" (description: "Verify python3, pipenv, podman, podman compose are installed")
     - "No" (description: "Skip checks and proceed directly")

3. Based on the user's answers, execute the appropriate steps:

   **If environment check = Yes:**
   - Run `python3 --version`, `unset PIPENV_PIPFILE && pipenv --version`, `podman --version`, `podman compose version`
   - Report any missing tools and suggest installation

   **Always (before any other setup):**
   - Initialize git submodules: `git submodule update --init --recursive`
   - Bootstrap `.env` file: if `.env` does not exist, create it with the defaults from `setup_init.py`'s `bootstrap_env_file()`. If it exists, verify `UNLEASH_TOKEN`, `INVENTORY_DB_USER`, and `INVENTORY_DB_PASS` are set (non-empty, non-commented). Append any missing variables with defaults. This is required because `dev.yml` uses `${UNLEASH_TOKEN:?}` which fails if the variable is unset.

   **If database = Fresh start:**
   - Warn the user this will delete existing data
   - Run `rm -rf ~/.pg_data && mkdir -p ~/.pg_data`

   **If database = Keep existing:**
   - Run `mkdir -p ~/.pg_data`

   **If dependencies = Full install:**
   - Run `unset PIPENV_PIPFILE && pipenv install --dev`

   **If Podman services != Skip (before starting):**
   - Check for port conflicts: parse `dev.yml` to find all host port mappings, then use `python3 -c "import socket; s=socket.socket(); s.settimeout(1); print(s.connect_ex(('127.0.0.1', PORT)))"` for each port. If Podman services are already running (`podman compose -f dev.yml ps -q` returns output), skip the check. Report any conflicts and warn the user to stop conflicting processes.

   **If Podman services = All services:**
   - Run `podman compose -f dev.yml up -d`

   **If Podman services = Minimal:**
   - Run `podman compose -f dev.yml up -d db kafka zookeeper`

   **If Podman services != Skip (after starting):**
   - Wait for PostgreSQL: poll `podman compose -f dev.yml exec -T db pg_isready -h db`
   - Run migrations: `unset PIPENV_PIPFILE && INVENTORY_DB_HOST=localhost INVENTORY_DB_NAME=insights INVENTORY_DB_USER=insights INVENTORY_DB_PASS=insights pipenv run make upgrade_db`
   - Health check: `curl -sf http://localhost:8080/health`

4. Report results for each step that was executed.

5. Check if `kafka` is in `/etc/hosts`. If not, ask the user:
   - "Add '127.0.0.1 kafka' to /etc/hosts? (requires sudo)"
   - Options: "Yes" / "No"
   - If yes: `echo '127.0.0.1 kafka' | sudo tee -a /etc/hosts`
