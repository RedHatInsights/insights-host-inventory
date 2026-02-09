# /doctor - HBI Development Environment Health Check

Diagnose the health of all HBI development services and dependencies.

## Instructions

Run each of the following checks and report results in a summary table:

### 1. Podman Containers
- Run `podman compose -f dev.yml ps` to check container status
- Report which containers are running, stopped, or missing
- Expected containers: hbi-db, kafka, zookeeper, hbi-web, hbi-mq, unleash, minio, export-service, prometheus_gateway

### 2. PostgreSQL
- Run `podman compose -f dev.yml exec -T db pg_isready -h db`
- Report if PostgreSQL is accepting connections

### 3. Kafka
- Check if kafka container is running: `podman compose -f dev.yml ps kafka`
- Check if port 29092 is reachable: `podman compose -f dev.yml exec -T kafka kafka-broker-api-versions --bootstrap-server localhost:29092 2>&1 | head -1`

### 4. HBI Web Service
- Run `curl -sf http://localhost:8080/health`
- Report the version response or connection error

### 5. Database Migration Status
- Run with local env: `unset PIPENV_PIPFILE && INVENTORY_DB_HOST=localhost INVENTORY_DB_NAME=insights INVENTORY_DB_USER=insights INVENTORY_DB_PASS=insights FLASK_APP=manage.py pipenv run flask db current`
- Report current migration head

### 6. Python Environment
- Check `python3 --version`
- Check `pipenv --version`
- Check if virtual environment exists: `unset PIPENV_PIPFILE && pipenv --venv`

### 7. Git Submodules
- Run `git submodule status` to check submodule state
- Report if submodules are initialized (e.g., `librdkafka`)
- If a submodule shows a `-` prefix, it is not initialized — suggest `git submodule update --init --recursive`

### 8. Hosts File
- Check if `kafka` entry exists in `/etc/hosts`

### Summary
Present results as a table:

| Check | Status | Details |
|-------|--------|---------|
| Podman Containers | OK/WARN/FAIL | N/M running |
| PostgreSQL | OK/FAIL | accepting connections / not ready |
| Kafka | OK/FAIL | broker reachable / not reachable |
| HBI Web Service | OK/FAIL | version or error |
| DB Migrations | OK/WARN | current head or error |
| Python Environment | OK/FAIL | version info |
| Git Submodules | OK/WARN | initialized / not initialized |
| Hosts File | OK/WARN | kafka entry present/missing |

If any checks fail, provide remediation steps.
