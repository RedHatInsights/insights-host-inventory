# Host Based Inventory (HBI)

You've arrived at the repo for the backend of the Host Based Inventory (HBI).
If you're looking for API, integration or user documentation for HBI
please see the
[Insights Inventory Documentation](https://url.corp.redhat.com/hbi).

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
    - [Create Hosts Data](#create-hosts-data)
    - [Run the export service](#run-the-export-service)
    - [Testing](#testing)
- [Running the webserver locally](#running-the-webserver-locally)
- [Legacy Support](#legacy-support)
- [Identity](#identity)
    - [API requests](#api-requests)
    - [Using the local Swagger UI to test the API](#using-the-local-swagger-ui-to-test-the-api)
    - [Kafka messages](#kafka-messages)
    - [Identity enforcement](#identity-enforcement)
- [Payload Tracker integration](#payload-tracker-integration)
- [Database migrations](#database-migrations)
- [Docker builds](#docker-builds)
- [Metrics](#metrics)
- [Documentation](#documentation)
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
- **Python 3.12.x**: The recommended version for this project.
- **pipenv**: For managing Python dependencies.

### Environment setup

#### PostgreSQL configuration

Local development also requires the `pg_config` file, which is installed with the postgres developer library.
To install this, use the command appropriate for your system:

##### Fedora/Centos

```bash
sudo dnf install libpq-devel postgresql python3.12-devel
```

##### Debian/Ubuntu

```bash
sudo apt-get install libpq-dev postgresql python3.12-dev
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
BYPASS_KESSEL="true"
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
This includes the web server, MQ server, database, Kafka, and other infrastructure services.

**Note:** This repository uses git submodules (e.g., `librdkafka`). If you haven't already, clone the repository with submodules:

```bash
git clone --recurse-submodules https://github.com/RedHatInsights/insights-host-inventory.git
```

Or, if you've already cloned without submodules, initialize them with:

```bash
git submodule update --init --recursive
```

Start the services with the following command:

```bash
docker compose -f dev.yml up -d
```

The web and MQ servers will automatically start when this command is run.
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

### Create Hosts Data

- Note: You may need to add a host entry for Kafka:

```bash
echo "127.0.0.1   kafka" | sudo tee -a /etc/hosts
```

To create one host(s), run the following command:

```bash
make run_inv_mq_service_test_producer NUM_HOSTS=800
```

- By default, it creates one host if `NUM_HOSTS` is not specified.
- Optionally, you may need to pass `INVENTORY_HOST_ACCOUNT=5894300` to the command above to override the default `org_id` (`321`)
- Optionally, you may want to create different types of hosts by passing `HOST_TYPE=[sap|rhsm|qpc]`. By default, it will create standard hosts with basic system profile data.

#### Using the Enhanced Kafka Producer

The new Kafka producer supports creating different types of hosts with various configurations:

```bash
# Create default hosts
python utils/kafka_producer.py --num-hosts 10

# Create RHSM hosts
python utils/kafka_producer.py --host-type rhsm --num-hosts 5

# Create QPC hosts
python utils/kafka_producer.py --host-type qpc --num-hosts 3

# Create SAP hosts
python utils/kafka_producer.py --host-type sap --num-hosts 2

# List available host types
python utils/kafka_producer.py --list-types

# Use custom Kafka settings
python utils/kafka_producer.py --host-type sap --num-hosts 5 \
  --bootstrap-servers localhost:29092 \
  --topic platform.inventory.host-ingress
```

**Available Host Types:**
- `default`: Standard hosts with basic system profile data
- `rhsm`: Red Hat Subscription Manager hosts with RHSM-specific facts and metadata
- `qpc`: Quipucords Product Catalog hosts with discovery-specific data
- `sap`: SAP hosts with SAP workloads data in the dynamic system profile

**Environment Variables:**
- `NUM_HOSTS`: Number of hosts to create (default: 1)
- `HOST_TYPE`: Default host type (default: "default")
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka bootstrap servers (default: "localhost:29092")
- `KAFKA_HOST_INGRESS_TOPIC`: Kafka topic for host ingress (default: "platform.inventory.host-ingress")

#### Run the Export Service

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

**Want to learn more?** See the [Export Service documentation](https://url.corp.redhat.com/export-service) for details on how the export service works.

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

#### IQE Integration Tests

The repository now includes the IQE (Insights QE) test suite in the `iqe-host-inventory-plugin/` directory. These are comprehensive integration tests that cover:
- REST API endpoints (backend tests)
- UI tests (frontend tests)
- Database tests
- Resilience tests
- RBAC tests
- Notifications tests

**Running IQE Tests Locally:**

The IQE tests require special dependencies and configuration. For detailed instructions on running IQE tests locally, see the [IQE README](iqe-host-inventory-plugin/README.md).

**PR Checks:**

The IQE smoke tests are automatically run as part of the PR check pipeline. When `IQE_INSTALL_LOCAL_PLUGIN=true` (default), the pr_check.sh script:
1. Builds the PR commit image
2. Runs unit tests
3. Deploys to an ephemeral environment
4. Deploys a CJI (ClowdJobInvocation) pod with `--debug-pod` option
5. Copies the local IQE plugin from `iqe-host-inventory-plugin/` to the CJI pod
6. Installs the plugin in editable mode inside the pod
7. Runs IQE smoke tests (tests marked with `backend and smoke`) with your local changes
8. Collects test artifacts

This ensures that every PR is tested with the exact IQE test code in the repository, not the version from Nexus. The local IQE plugin deployment is controlled by the `IQE_INSTALL_LOCAL_PLUGIN` environment variable set in `pr_check_common.sh`.

**How it works:**
- `deploy_ephemeral_env.sh`: Creates the ephemeral namespace and deploys HBI
- `run_cji_with_local_plugin.sh`: Deploys the CJI pod, copies local plugin, installs it, and runs tests
- `post_test_results.sh`: Collects and publishes test results

## Running the webserver locally

When running the web server locally for development, the Prometheus configuration is done automatically.
You can run the web server directly using this command:

```bash
python3 run_gunicorn.py
```

Note: If you started services with `docker compose -f dev.yml up -d`, the web server is already running in the `hbi-web` container.

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

### Using the local Swagger UI to test the API

The Swagger UI provides an interactive interface for testing the API endpoints locally.

**Prerequisites:**
- Ensure the web service is running (via `docker compose -f dev.yml up -d`)
- The service should be accessible at `http://localhost:8080/api/inventory/v1/ui/`

**Access Swagger UI:**

1. Open your browser and navigate to: `http://localhost:8080/api/inventory/v1/ui/`

2. The Swagger UI will display all available API endpoints with their documentation.

**Testing API Requests:**

By default, RBAC is bypassed in local development (via `BYPASS_RBAC="true"` in
`.env`), so you can make requests without authentication. However, you still
need to provide a valid identity header for some endpoints.

**Option 1: Using the Swagger UI Interface**

1. Add the identity header:
   - Click on "Authorize" (On the top right of the page)
   - Header name: `x-rh-identity`
   - Header value: `eyJpZGVudGl0eSI6eyJvcmdfaWQiOiJ0ZXN0IiwidHlwZSI6IlVzZXIiLCJhdXRoX3R5cGUiOiJiYXNpYy1hdXRoIiwidXNlciI6eyJ1c2VybmFtZSI6InR1c2VyQHJlZGhhdC5jb20iLCJlbWFpbCI6InR1c2VyQHJlZGhhdC5jb20iLCJmaXJzdF9uYW1lIjoidGVzdCIsImxhc3RfbmFtZSI6InVzZXIiLCJpc19hY3RpdmUiOnRydWUsImlzX29yZ19hZG1pbiI6ZmFsc2UsImlzX2ludGVybmFsIjp0cnVlLCJsb2NhbGUiOiJlbl9VUyJ9fX0=`
2. Click on an endpoint (e.g., `GET /hosts`)
3. Click the "Try it out" button
4. Fill in any required parameters
5. Click "Execute"

**Option 2: Using curl (from Swagger UI)**

After configuring your request in the Swagger UI, you can copy the generated curl command and run it directly from your terminal.

**Common Test Identity Headers:**

User identity (for general API testing):
```
x-rh-identity: eyJpZGVudGl0eSI6eyJvcmdfaWQiOiJ0ZXN0IiwidHlwZSI6IlVzZXIiLCJhdXRoX3R5cGUiOiJiYXNpYy1hdXRoIiwidXNlciI6eyJ1c2VybmFtZSI6InR1c2VyQHJlZGhhdC5jb20iLCJlbWFpbCI6InR1c2VyQHJlZGhhdC5jb20iLCJmaXJzdF9uYW1lIjoidGVzdCIsImxhc3RfbmFtZSI6InVzZXIiLCJpc19hY3RpdmUiOnRydWUsImlzX29yZ19hZG1pbiI6ZmFsc2UsImlzX2ludGVybmFsIjp0cnVlLCJsb2NhbGUiOiJlbl9VUyJ9fX0=
```

System identity (for system-level operations):
```
x-rh-identity: eyJpZGVudGl0eSI6eyJvcmdfaWQiOiAidGVzdCIsICJhdXRoX3R5cGUiOiAiY2VydC1hdXRoIiwgInN5c3RlbSI6IHsiY2VydF90eXBlIjogInN5c3RlbSIsICJjbiI6ICJwbHhpMTN5MS05OXV0LTNyZGYtYmMxMC04NG9wZjkwNGxmYWQifSwidHlwZSI6ICJTeXN0ZW0ifX0=
```

**Example: Listing Hosts**

1. Add the `x-rh-identity` header (see above)
2. Navigate to `GET /hosts` endpoint in Swagger UI
3. Click "Try it out"
4. Set query parameters as needed (e.g., `per_page: 10`)
5. Click "Execute"
6. View the response in the "Responses" section

### Kafka Messages

For Kafka messages, the Identity must be set in the `platform_metadata.b64_identity` field.

**Want to learn more?** For comprehensive documentation on message formats, validation, and the host insertion and update flow, see [Host Insertion](https://url.corp.redhat.com/hbi-host-insertion) in the HBI documentation.

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

### Running Database Migrations

In managed environments, the database migrations are run by the `run-db-migrations` job.
This job runs once per release, as its name contains the image tag (`run-db-migrations-<IMAGE_TAG>).

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

## Documentation

The source of the [HBI documentation](https://url.corp.redhat.com/hbi) is located in the [docs/ folder](docs/). Any change to service behavior must also be reflected in the documentation to keep it up to date.

New files added to the folder will be accessible on the InScope HBI page, but renaming existing files can break direct links.

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
    * smoke (the most important) IQE tests
* `ci.ext.devshift.net PR build - All tests` runs _all_ the IQE tests (with disabled RBAC) on the PR's code.
* `ci.ext.devshift.net PR build - RBAC tests` runs RBAC integration IQE tests on the PR's code.
* [host-inventory build-master](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-gh-build-master/)
  builds the container image, and pushes it to Quay, where it is scanned for vulnerabilities.

Should any of these fail this is indicated directly on the pull request.

When all of these checks pass and a reviewer approves the changes the pull request can be merged by someone from
the [@RedHatInsights/host-based-inventory-committers](https://github.com/orgs/RedHatInsights/teams/host-based-inventory-committers)
team.

### 2. Latest image and Stage deployment

When a pull request is merged to master, a new container image is built and tagged
as [insights-inventory:latest](https://quay.io/repository/cloudservices/insights-inventory?tab=tags).
This image is then automatically deployed to
the [Stage environment](https://console-openshift-console.apps.crcs02ue1.urby.p1.openshiftapps.com/k8s/cluster/projects/host-inventory-stage).

### 3. QE testing in the stage environment

Once the image lands in the Stage environment, the QE testing can begin.
People in [@team-inventory-dev](https://redhat.enterprise.slack.com/admin/user_groups/S04F8720GKG) run
the full IQE test suite against Stage, and then report the results in
the [#team-insights-inventory channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T).
Everything that needs to be done before we can do a Prod release is mentioned in the
"Promoting deployments to Prod" section of the
[iqe-host-inventory-plugin README](https://gitlab.cee.redhat.com/insights-qe/iqe-host-inventory-plugin/-/blob/master/README.md#promoting-deployments-to-prod)

### 4. Promoting the image to the production environment

In order to promote a new image to the production environment, it is necessary to update
the [deploy-clowder.yml](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml)
file.
The `ref` parameter on the `prod-host-inventory-prod` namespace needs to be updated to the SHA of the validated image.
Also, if there are new commits in [cyndi-operator](https://github.com/RedHatInsights/cyndi-operator) or
[xjoin-kafka-connect](https://github.com/RedHatInsights/xjoin-kafka-connect) repositories,
those should be deployed together with HBI as well.

#### Using app-interface-bot

If xjoin-kafka-connect doesn't have new commits that need to be deployed (it's a very stable repo,
so deploying new version of it to Prod is very rare), and we don't need to make any app-interface
config changes, it is preferred to use
[app-interface-bot](https://gitlab.cee.redhat.com/osbuild/app-interface-bot) to create the
release MR. This bot automatically scans the repositories and creates a release MR with the latest
commits. It also adds all released PRs and linked Jira cards to the description of the MR.

To run the app-interface-bot go to
[pipelines](https://gitlab.cee.redhat.com/osbuild/app-interface-bot/-/pipelines) and click
"New pipeline" in the top right corner of the page. Now select "host-inventory" as `HMS_SERVICE`,
and put "master" (to release the latest commit) to `HOST_INVENTORY_BACKEND` and `CYNDI_OPERATOR`
variables. If the CI is failing in GitHub on the latest commit for an irrelevant reason, and you are
sure that it is OK, also choose "--force" on the `FORCE` variable. Now you can click "New pipeline"
and the bot will create the release MR for you in a few seconds. When it's done, it will send a
Slack message to `#insights-experiences-release` channel with the link to the MR
([example](https://redhat-internal.slack.com/archives/C061D8JQ8BE/p1756802843458909)).

The bot is configured to automatically create these release MRs on Mondays. Every time
it does so, carefully check if the release doesn't need any config change. For example, if the
release includes a DB migration, then there is a high chance that we want to reduce the number of
MQ replicas during this migration. In that case, feel free to close the MR either manually, or by
creating a new [pipeline](https://gitlab.cee.redhat.com/osbuild/app-interface-bot/-/pipelines) and
adding the MR ID to the `CLOSE_MR` variable. Then you can create a new release MR manually with
everything that's needed, and you can copy the description from the bot's release MR.

For the CI pipeline to run tests on your fork, you'll need to add
[@devtools-bot](https://gitlab.cee.redhat.com/devtools-bot) as a Maintainer. See this
[guide](https://docs.gitlab.com/ee/user/project/members/share_project_with_groups.html#sharing-a-project-with-a-group-of-users)
on how to do that.

[Example release MR](https://gitlab.cee.redhat.com/service/app-interface/-/merge_requests/155681)

After the MR has been opened, carefully check all PRs that are going to be released and if everything is
OK and well tested (all Jira cards that are being released are in "Release pending" state, there is
no "On QA" Jira), then ask someone else from the Inventory team to also check the release MR and
approve it by adding a `/lgtm` comment.
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

### Rollback process

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
[Running a Special Job](https://url.corp.redhat.com/running-special-job) describes how to accomplish it.

### Debugging local code with services deployed into Kubernetes namespaces

Making local code work with the services running in Kubernetes requires some actions
provided in [Debugging Local Code with Services Deployed into Kubernetes Namespaces](docs/debug_local_code_k8s.md).

## Contributing

### Pre-commit Hooks

The repository uses [pre-commit](https://pre-commit.com) to enforce code style. Install pre-commit hooks:

```bash
pre-commit install
```

If inside the Red Hat network, also ensure `rh-pre-commit` is installed as per
instructions [here](https://url.corp.redhat.com/rh-pre-commit#quickstart-install).

## GABI Query Tool (interactive and non-interactive)

Send SQL queries to a GABI endpoint either interactively (REPL) or non-interactively (file/stdin). Results can be
displayed as a formatted table, raw JSON, or both.

### Prerequisites

- Logged into your OpenShift cluster via `oc` if using default authentication and URL detection.

### Usage

- Interactive REPL (default environment: prod):
  ```bash
  ./utils/run_gabi_interactive.py --interactive
  ```
- Interactive on stage:
  ```bash
  ./utils/run_gabi_interactive.py --env stage --interactive
  ```
- Explicit URL override (interactive):
  ```bash
  ./utils/run_gabi_interactive.py --url https://gabi-host-inventory-stage.apps.<cluster>/query --interactive
  ```
- Non-interactive from file:
  ```bash
  ./utils/run_gabi_interactive.py --env stage --file query.sql
  ```
- Non-interactive from stdin:
  ```bash
  cat query.sql | ./utils/run_gabi_interactive.py --env stage
  ```
- Output format control:
  ```bash
  # JSON only
  ./utils/run_gabi_interactive.py --file query.sql --format json

  # Both table and JSON
  ./utils/run_gabi_interactive.py --file query.sql --format both
  ```

### Command-Line Arguments

- `--env {prod,stage}`: Chooses the target environment (defaults to prod). Determines the app used for URL derivation.
- `--url <API_ENDPOINT_URL>`: Explicit GABI endpoint. Overrides the derived URL.
- `--auth <AUTH_TOKEN>`: Bearer token. Defaults to token from `oc whoami -t`.
- `--file <SQL_QUERY_FILE>`: Run a single query from a file (non-interactive).
- `--interactive`: Run in REPL mode and enter multiple queries.
- `--format {table,json,both}`: Output as pretty table, raw JSON, or both (default: table).

### Example (interactive)

```bash
./utils/run_gabi_interactive.py --env stage --interactive
Connected to https://gabi-host-inventory-stage.apps.example.com/query
Type 'exit' or 'quit' to end the session.

Enter your SQL query (press Enter on an empty line to submit):
SELECT COUNT(*) FROM hbi.hosts;
```

### Example (non-interactive)

```bash
./utils/run_gabi_interactive.py --env stage --file query.sql --format both
```
