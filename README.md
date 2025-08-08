# Host Based Inventory (HBI)

You've arrived at the repo for the backend of the Host Based Inventory (HBI).
If you're looking for API, integration or user documentation for HBI
please see
the [Inventory section in our Platform Docs site](https://consoledot.pages.redhat.com/docs/dev/services/inventory.html).

## Table of contents

- [Getting started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Environment setup](#environment-setup)
        - [PostgreSQL configuration](#postgresql-configuration)
        - [Environment variables](#environment-variables)
        - [Create virtual environment](#create-virtual-environment)
        - [Create database data directory](#create-database-data-directory)
        - [Start dependent services](#start-dependent-services)
    - [Run database migrations](#run-database-migrations)
    - [Run the service](#run-the-service)
    - [Testing](#testing)
- [Running the webserver locally](#running-the-webserver-locally)
- [Running all services locally](#running-all-services-locally)
- [Legacy Support](#legacy-support)
- [Identity](#identity)
    - [API requests](#api-requests)
    - [Kafka messages](#kafka-messages)
    - [Identity enforcement](#identity-enforcement)
- [Payload Tracker integration](#payload-tracker-integration)
- [Database migrations](#database-migrations)
- [Schema dumps (for replication subscribers)](#schema-dumps-for-replication-subscribers)
- [Docker builds](#docker-builds)
- [Metrics](#metrics)
- [Release process](#release-process)
    - [Pull request](#1-pull-request)
    - [Latest image and smoke tests](#2-latest-image-and-smoke-tests)
    - [QE Testing in stage environment](#3-qe-testing-in-the-stage-environment)
    - [Promoting to production](#4-promoting-the-image-to-the-production-environment)
    - [Monitoring of deployment](#5-monitoring-of-deployment)
- [Rollback process](#rollback-process)
- [Updating the System Profile](#updating-the-system-profile)
- [Logging System Profile fields](#logging-system-profile-fields)
- [Running ad hoc jobs using a different image](#running-ad-hoc-jobs-using-a-different-image)
- [Debugging local code with services deployed into Kubernetes namespaces](#debugging-local-code-with-services-deployed-into-kubernetes-namespaces)
- [Contributing](#contributing)

## Getting started

### Prerequisites

Before starting, ensure you have the following installed on your system:

- **Docker**: For running containers and services.
- **Python 3.11.x**: The recommended version for this project.
- **pipenv**: For managing Python dependencies.

### Environment setup

#### PostgreSQL configuration

Local development also requires the `pg_config` file, which is installed with the postgres developer library.
To install this, use the command appropriate for your system:

##### Fedora/Centos

```bash
sudo dnf install libpq-devel postgresql
```

##### Debian/Ubuntu

```bash
sudo apt-get install libpq-dev postgresql
```

##### MacOS (using Homebrew)

```bash
brew install postgresql@16
```

#### Environment variables

Create a `.env` file in your project root with the following content. Replace placeholders with
appropriate values for your environment.

```bash
cat > ${PWD}/.env<<EOF
# RUNNING HBI Locally
PROMETHEUS_MULTIPROC_DIR=/tmp
BYPASS_RBAC="true"
BYPASS_UNLEASH="true"
# Optional legacy prefix configuration
# PATH_PREFIX="/r/insights/platform"
APP_NAME="inventory"
INVENTORY_DB_USER="insights"
INVENTORY_DB_PASS="insights"
INVENTORY_DB_HOST="localhost"
INVENTORY_DB_NAME="insights"
INVENTORY_DB_POOL_TIMEOUT="5"
INVENTORY_DB_POOL_SIZE="5"
INVENTORY_DB_SSL_MODE=""
INVENTORY_DB_SSL_CERT=""
UNLEASH_TOKEN='*:*.dbffffc83b1f92eeaf133a7eb878d4c58231acc159b5e1478ce53cfc'
UNLEASH_CACHE_DIR=./.unleash
UNLEASH_URL="http://localhost:4242/api"
# Kafka Export Service Configuration
KAFKA_EXPORT_SERVICE_TOPIC="platform.export.requests"
EOF
```

After creating the file, source it to set the environment variables:

```bash
source .env
```

### Create virtual environment

1. **Install dependencies**:

```bash
pipenv install --dev
```

2. **Activate virtual environment**:

```bash
pipenv shell
```

### Create database data directory

Provide a local directory for database persistence:

```bash
mkdir ~/.pg_data
```

If using a different directory, update the `volumes` section in [dev.yml](dev.yml).

### Start dependent services

All dependent services are managed by Docker Compose and are listed in the [dev.yml](dev.yml) file.
Start them with the following command:

```bash
docker compose -f dev.yml up -d
```

By default, the database container will use a bit of local storage so that data you enter will persist across multiple
starts of the container.
If you want to destroy that data do the following:

```bash
docker compose -f dev.yml down
rm -r ~/.pg_data # or a another directory you defined in volumes
```

### Run database migrations

```bash
make upgrade_db
```

### Run the service

1. **Run the MQ Service**:

```bash
make run_inv_mq_service
```

- Note: You may need to add a host entry for Kafka:

```bash
echo "127.0.0.1   kafka" | sudo tee -a /etc/hosts
```

2. **Create Hosts Data**:

```bash
make run_inv_mq_service_test_producer NUM_HOSTS=800
```

- By default, it creates one host if `NUM_HOSTS` is not specified.

3. **Run the Export Service**:

```bash
pipenv shell
make run_inv_export_service
```

In another terminal, generate events for the export service with:

```bash
make sample-request-create-export
```

By default, it will send a json format request. To modify the data format, use:

```bash
make sample-request-create-export format=[json|csv]
```

### Testing

You can run the tests using pytest:

```bash
pytest --cov=.
```

Or run individual tests:

```bash
# To run all tests in a specific file:
pytest tests/test_api_auth.py
# To run a specific test
pytest tests/test_api_auth.py::test_validate_valid_identity
```

- Note: Ensure DB-related environment variables are set before running tests.

## Running the webserver locally

Prometheus was designed to run in a multithreaded
environment whereas gunicorn uses a multiprocess
architecture. As a result, there is some work
to be done to make prometheus integrate with
gunicorn.

A temp directory for prometheus needs to be created
before the server starts. The PROMETHEUS_MULTIPROC_DIR
environment needs to point to this directory. The
contents of this directory need to be removed between
runs.

If running the server in a cluster, you can use this command:

```bash
gunicorn -c gunicorn.conf.py run
```

When running the server locally for development, the Prometheus configuration is done automatically.
You can run the server locally using this command:

```bash
python3 run_gunicorn.py
```

## Running all services locally

Use Honcho to run MQ and web services at once:

```bash
honcho start
```

## Legacy support

Some apps still need to use the legacy API path, which by default is `/r/insights/platform/inventory/v1/`.
In case legacy apps require this prefix to be changed, it can be modified using this environment variable:

```bash
export INVENTORY_LEGACY_API_URL="/r/insights/platform/inventory/api/v1"
```

## Identity

### API Requests

When testing the API, set the identity header in curl:

```curl
x-rh-identity: eyJpZGVudGl0eSI6eyJvcmdfaWQiOiJ0ZXN0IiwidHlwZSI6IlVzZXIiLCJhdXRoX3R5cGUiOiJiYXNpYy1hdXRoIiwidXNlciI6eyJ1c2VybmFtZSI6InR1c2VyQHJlZGhhdC5jb20iLCJlbWFpbCI6InR1c2VyQHJlZGhhdC5jb20iLCJmaXJzdF9uYW1lIjoidGVzdCIsImxhc3RfbmFtZSI6InVzZXIiLCJpc19hY3RpdmUiOnRydWUsImlzX29yZ19hZG1pbiI6ZmFsc2UsImlzX2ludGVybmFsIjp0cnVlLCJsb2NhbGUiOiJlbl9VUyJ9fX0=
```

This is the Base64 encoding of:

```json
{
  "identity": {
    "org_id": "test",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {
      "username": "tuser@redhat.com",
      "email": "tuser@redhat.com",
      "first_name": "test",
      "last_name": "user",
      "is_active": true,
      "is_org_admin": false,
      "is_internal": true,
      "locale": "en_US"
    }
  }
}
```

The above header has the "User" identity type, but it's possible to use a "System" type header as well.

```curl
x-rh-identity: eyJpZGVudGl0eSI6eyJvcmdfaWQiOiAidGVzdCIsICJhdXRoX3R5cGUiOiAiY2VydC1hdXRoIiwgInN5c3RlbSI6IHsiY2VydF90eXBlIjogInN5c3RlbSIsICJjbiI6ICJwbHhpMTN5MS05OXV0LTNyZGYtYmMxMC04NG9wZjkwNGxmYWQifSwidHlwZSI6ICJTeXN0ZW0ifX0=
```

This is the Base64 encoding of:

```json
{
  "identity": {
    "org_id": "test",
    "auth_type": "cert-auth",
    "system": {
      "cert_type": "system",
      "cn": "plxi13y1-99ut-3rdf-bc10-84opf904lfad"
    },
    "type": "System"
  }
}
```

If you want to encode other JSON documents, you can use the following command:

```bash
echo -n '{"identity": {"org_id": "0000001", "type": "System"}}' | base64 -w0
```

### Kafka Messages

For Kafka messages, the Identity must be set in the `platform_metadata.b64_identity` field.

### Identity Enforcement

The Identity provided limits access to specific hosts.
For API requests, the user can only access Hosts which have the same Org ID as the provided Identity.
For Host updates via Kafka messages, A Host can only be updated if not only the Org ID matches,
but also the `Host.system_profile.owner_id` matches the provided `identity.system.cn` value.

## Payload Tracker integration

The inventory service integrates with the Payload Tracker service. Configure it using these environment variables:

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
PAYLOAD_TRACKER_KAFKA_TOPIC=platform.payload-status
PAYLOAD_TRACKER_SERVICE_NAME=inventory
PAYLOAD_TRACKER_ENABLED=true
```

* **Enabled**: Set `PAYLOAD_TRACKER_ENABLED=false` to disable the tracker.
* **Usage**: The tracker logs success or errors for each payload operation. For example, if a payload contains multiple
  hosts and one fails, it's logged as a "processing_error" but doesn't mark the entire payload as failed.

## Database Migrations

Generate new migration scripts with:

```bash
make migrate_db message="Description of your changes"
```

* **Replicated Tables**: If your migration affects replicated tables, ensure you create and apply migrations for them
  first. See [app_migrations/README.md](app_migrations/README.md) for details.

## Schema Dumps (for replication subscribers)

Capture the current HBI schema state with:

```bash
make gen_hbi_schema_dump
```

* Generates a SQL file in `app_migrations` named `hbi_schema_<YYYY-MM-dd>.sql`.
* Creates a symbolic link `hbi_schema_latest.sql` pointing to the latest dump.

_Note_: Use the optional `SCHEMA_VERSION` variable to customize the filename.

## Docker Builds

Build local development containers with:

```bash
docker build . -f dev.dockerfile -t inventory:dev
```

* **Note**: Some packages require a subscription. Ensure your host has access to valid RHEL content.

## Metrics

Prometheus integration provides monitoring endpoints:

- `/health`: Liveness probe endpoint.
- `/metrics`: Prometheus metrics endpoint.
- `/version`: Returns build version info.

Cron jobs (`reaper`, `sp-validator`) push metrics to
a [Prometheus Pushgateway](https://github.com/prometheus/pushgateway/) at `PROMETHEUS_PUSHGATEWAY` (default:
`localhost:9091`).

## Release process

This section describes the process of getting a code change from a pull request all the way to production.

### 1. Pull request

It all starts with a [pull request](https://github.com/RedHatInsights/insights-host-inventory/pulls).
When a new pull request is opened, some jobs are run automatically.
These jobs are defined in
app-interface [here](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/build.yml).

* [host-inventory pr-checker](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-pr-check) runs the
  following:
    * [database migrations](#database-migrations)
    * [code style checks](#contributing)
    * unit tests
* `ci.ext.devshift.net PR build - All tests` runs _all_ the IQE tests on the PR's code.
* [host-inventory build-master](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-gh-build-master/)
  builds the container image, and pushes it to Quay, where it is scanned for vulnerabilities.

Should any of these fail this is indicated directly on the pull request.

When all of these checks pass and a reviewer approves the changes the pull request can be merged by someone from
the [@RedHatInsights/host-based-inventory-committers](https://github.com/orgs/RedHatInsights/teams/host-based-inventory-committers)
team.

### 2. Latest image and smoke tests

When a pull request is merged to master, a new container image is built and tagged
as [insights-inventory:latest](https://quay.io/repository/cloudservices/insights-inventory?tab=tags).
This image is then automatically deployed to
the [Stage environment](https://console-openshift-console.apps.crcs02ue1.urby.p1.openshiftapps.com/k8s/cluster/projects/host-inventory-stage).

### 3. QE testing in the stage environment

Once the image lands in the Stage environment, the QE testing can begin.
People in [@team-inventory-dev](https://redhat.enterprise.slack.com/admin/user_groups/S04F8720GKG) run
the full IQE test suite against Stage, and then report the results in
the [#team-insights-inventory channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T).

### 4. Promoting the image to the production environment

In order to promote a new image to the production environment, it is necessary to update
the [deploy-clowder.yml](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml)
file.
The `ref` parameter on the `prod-host-inventory-prod` namespace needs to be updated to the SHA of the validated image.

Once the change has been made, submit a merge request
to [app-interface](https://gitlab.cee.redhat.com/service/app-interface).
For the CI pipeline to run tests on your fork, you'll need to
add [@devtools-bot](https://gitlab.cee.redhat.com/devtools-bot) as a Maintainer.
See
this [guide](https://docs.gitlab.com/ee/user/project/members/share_project_with_groups.html#sharing-a-project-with-a-group-of-users)
on how to do that.

After the MR has been opened, somebody
from `AppSRE/insights-host-inventory` will review and
approve the MR by adding a `/lgtm` comment.
Afterward, the MR will be merged automatically and the changes will be deployed to the production environment.
The engineer who approved the MR is then **responsible for monitoring of the rollout of the new image**.

Once that happens,
contact [@team-inventory-dev](https://redhat.enterprise.slack.com/admin/user_groups/S04F8720GKG) and
request the image to be re-tested in the production environment.
The new image will also be tested automatically when
the [Full Prod Check pipeline](https://jenkins-csb-insights-qe-main.dno.corp.redhat.com/job/inventory/job/backend/job/-prod-basic/)
is run (twice daily).

### 5. Monitoring of deployment

It is essential to monitor the health of the service during and after the production deployment.
A non-exhaustive list of things to watch includes:

- Monitor deployment in:
    - OpenShift
      namespace: [host-inventory-prod](https://console-openshift-console.apps.crcp01ue1.o9m8.p1.openshiftapps.com/k8s/cluster/projects/host-inventory-prod)
        - primarily ensure that the new pods are spun up properly
    - Slack channel: [Inventory Slack Channel](https://app.slack.com/client/T027F3GAJ/C01A49ZGQ05)
        - for any inventory-related Prometheus alerts
    - Grafana
      dashboard: [Inventory Dashboard](https://grafana.app-sre.devshift.net/d/EiIhtC0Wa/inventory?orgId=1&refresh=5m)
        - for any anomalies such as error rate or consumer lag
    - Kibana
      logs <a href="https://kibana.apps.crcp01ue1.o9m8.p1.openshiftapps.com/app/kibana#/discover?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-24h,to:now))&a=(columns:!(_source),filters:!(),index:'43c5fed0-d5ce-11ea-b58c-a7c95afd7a5d',interval:auto,query:(language:lucene,query:'@log_group:%20%22host-inventory-prod%22%20AND%20levelname:%20ERROR'),sort:!(!('@timestamp',desc)))">
      here</a>
        - for any error-level log entries

## Rollback process

Should unexpected problems occur during the deployment,
it is possible to do a rollback.
This is done by updating the ref parameter in `deploy-clowder.yml` to point to the previous commit SHA,
or by reverting the MR that triggered the production deployment.

## Updating the System Profile

In order to add or update a field on the System Profile, first follow the instructions in
the [inventory-schemas repo](https://github.com/RedHatInsights/inventory-schemas#contributing).
After an inventory-schemas PR has been accepted and merged, HBI must be updated to keep its own schema in sync.
To do this, simply run this command:

```bash
make update-schema
```

This will pull the latest version of the System Profile schema from inventory-schemas and update files as necessary.
Open a PR with these changes, and it will be reviewed and merged as per [the standard process](#release-process).

## Logging System Profile Fields

Use the environment variable SP_FIELDS_TO_LOG to log the System Profile fields of a host.
These fields are logged when adding, updating or deleting a host from inventory.

```bash
SP_FIELDS_TO_LOG="cpu_model,disk_devices"
```

This logging helps with debugging hosts in Kibana.

## Running ad hoc jobs using a different image

There may be a job `ClowdJobInvocation` which requires using a special image that is different
from the one used by the parent application, i.e. host-inventory.
Clowder out-of-the-box does not allow it.
[Running a Special Job](docs/running_special_job.md) describes how to accomplish it.

### Debugging local code with services deployed into Kubernetes namespaces

Making local code work with the services running in Kubernetes requires some actions
provided [here](docs/debug_local_code_targeting_ephemeral_namespace.md).

## Contributing

### Pre-commit Hooks

The repository uses [pre-commit](https://pre-commit.com) to enforce code style. Install pre-commit hooks:

```bash
pre-commit install
```

If inside the Red Hat network, also ensure `rh-pre-commit` is installed as per
instructions [here](https://url.corp.redhat.com/rh-pre-commit#quickstart-install).
