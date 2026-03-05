##@ HBI Dev Environment

-include .env
export
unexport PIPENV_PIPFILE

.PHONY: hbi-help
hbi-help: ## List all HBI make targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nHBI targets (mk/private.mk):\n\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' mk/private.mk
	@echo ""

.PHONY: hbi-up
hbi-up: ## Start all Podman Compose services
	podman compose -f dev.yml up -d

.PHONY: hbi-down
hbi-down: ## Stop all Podman Compose services
	podman compose -f dev.yml down

.PHONY: hbi-logs
hbi-logs: ## View service logs (set SERVICE= for a specific service)
	podman compose -f dev.yml logs -f $(SERVICE)

.PHONY: hbi-migrate
hbi-migrate: ## Run database migrations
	INVENTORY_DB_HOST=localhost INVENTORY_DB_NAME=insights INVENTORY_DB_USER=insights INVENTORY_DB_PASS=insights pipenv run make upgrade_db

.PHONY: hbi-test
hbi-test: ## Run tests with coverage (set ARGS= for extra args)
	pipenv run pytest --cov=. $(ARGS)

.PHONY: hbi-style
hbi-style: ## Run code style checks
	pipenv run make style

.PHONY: hbi-deps
hbi-deps: ## Install Python dependencies
	pipenv install --dev

.PHONY: hbi-health
hbi-health: ## Health check the web service
	curl -sf http://localhost:8080/health

.PHONY: hbi-ps
hbi-ps: ## Check Podman container status
	podman compose -f dev.yml ps

.PHONY: hbi-reset
hbi-reset: ## Reset development environment (stop services, remove db data)
	podman compose -f dev.yml down -v
	rm -rf ~/.pg_data
	rm -rf .claude/hooks/*.log
	mkdir -p ~/.pg_data

.PHONY: hbi-nuke
hbi-nuke: ## Full nuclear reset (containers, images, venv, db, caches — start from scratch)
	@echo "=== Stopping and removing all containers, volumes, and images ==="
	podman compose -f dev.yml down -v --rmi all || true
	@echo "=== Removing PostgreSQL data ==="
	rm -rf ~/.pg_data
	mkdir -p ~/.pg_data
	@echo "=== Removing pipenv virtual environment ==="
	pipenv --rm || true
	@echo "=== Removing MinIO data ==="
	rm -rf tmp/minio
	@echo "=== Removing Python caches ==="
	find . -type d -name __pycache__ -not -path './librdkafka/*' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov
	@echo "=== Removing Unleash cache ==="
	rm -rf .unleash/__pycache__ .unleash/.cache
	@echo "=== Removing hook logs ==="
	rm -rf .claude/hooks/*.log
	@echo ""
	@echo "=== Nuke complete. To rebuild, run: ==="
	@echo "  make hbi-deps     # reinstall Python dependencies"
	@echo "  make hbi-up       # start all services"
	@echo "  make hbi-migrate  # run database migrations"

##@ Claude Code

.PHONY: hbi-cldi
hbi-cldi: ## Deterministic codebase setup (via Claude Code --init)
	claude --model claude-opus-4-6 --dangerously-skip-permissions --init

.PHONY: hbi-cldm
hbi-cldm: ## Deterministic codebase maintenance (via Claude Code --maintenance)
	claude --model claude-opus-4-6 --dangerously-skip-permissions --maintenance

.PHONY: hbi-cldii
hbi-cldii: ## Agentic codebase setup (runs /hbi-install slash command)
	claude --model claude-opus-4-6 --dangerously-skip-permissions --init "/hbi-install"

.PHONY: hbi-cldit
hbi-cldit: ## Agentic interactive setup (runs /hbi-install-hil slash command)
	claude --model claude-opus-4-6 --dangerously-skip-permissions --init "/hbi-install true"

.PHONY: hbi-cldmm
hbi-cldmm: ## Agentic maintenance (runs /hbi-maintenance slash command)
	claude --model claude-opus-4-6 --dangerously-skip-permissions --maintenance "/hbi-maintenance"

.PHONY: hbi-cldiq
hbi-cldiq: ## Agentic IQE test environment setup (runs /hbi-iqe-setup slash command)
	claude --model claude-opus-4-6 --dangerously-skip-permissions "/hbi-iqe-setup"

.PHONY: hbi-cldss
hbi-cldss: ## Agentic API spec-sync check (runs /hbi-spec-sync slash command)
	claude --model claude-opus-4-6 --dangerously-skip-permissions "/hbi-spec-sync"

