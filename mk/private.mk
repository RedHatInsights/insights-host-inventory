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
