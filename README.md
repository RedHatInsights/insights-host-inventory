# Host Based Inventory

You've arrived at the repo for the backend of the Host Based Inventory (HBI).
If you're looking for API, integration or user documentation for HBI please see the [Inventory section in our Platform Docs site](https://consoledot.pages.redhat.com/docs/dev/services/inventory.html).

## Getting Started

### pg_config

Local development also requires the `pg_config` file, which is installed with the postgres developer library. To install this, use the command appropriate to your system:

#### Fedora/Centos

```bash
sudo dnf install libpq-devel
```

#### Debian/Ubuntu

```bash
sudo apt-get install libpq-dev
```

#### MacOS (using Homebrew)

```bash
brew install postgresql
```

### Configure the environment variables

To run *HBI* locally, first you will have to create an `.env` file with the following content.

*Warning*: This will overwrite an existing `.env` file if there is one at the root directory of your `git` repository.

```bash
cat > ${PWD}/.env<<EOF
# RUNNNING HBI Locally
PROMETHEUS_MULTIPROC_DIR=/tmp
prometheus_multiproc_dir=/tmp

BYPASS_RBAC="true"
BYPASS_UNLEASH="true"

# If you want to use the legacy prefix, otherwise don't set PATH_PREFIX
# PATH_PREFIX="/r/insights/platform"
# For testing notifications in stage/ephemeral, set this to the appropriate url
# PLATFORM_HOSTNAME="https://console.redhat.com"

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

# for export service
KAFKA_EXPORT_SERVICE_TOPIC="platform.export.requests"
EOF
```

Make all the appropriate changes as needed, and source it.

```bash
source .env
```

To force an ssl connection to the db set `INVENTORY_DB_SSL_MODE` to `"verify-full"`
and provide the path to the certificate you'd like to use.

### Install dependencies

This project uses `pipenv` to manage the development and deployment environments.
To set the project up for development, we recommend using [pyenv](https://github.com/pyenv/pyenv) to
install/manage the appropriate `Python` (currently `3.9.x`), `pip` and `pipenv` version.
Once you have `pipenv`, do the following:

```bash
pipenv install --dev
```

Afterwards you can activate the virtual environment by running:

```bash
pipenv shell
```

Included is a docker-compose file `dev.yml` that will start a postgres database that is
useful for development.

```bash
docker compose -f dev.yml up
```

### Initialize the database

Run the following commands to run the db migration scripts which will
maintain the db tables.

The database migration scripts determine the DB location, username,
password and db name from the `INVENTORY_DB_HOST`, `INVENTORY_DB_USER`,
`INVENTORY_DB_PASS` and `INVENTORY_DB_NAME` environment variables present in
the `.env` file.

```bash
make upgrade_db
```

By default the database container will use a bit of local storage so that data
you enter will persist across multiple starts of the container. If you
want to destroy that data do the following:

```bash
docker compose -f dev.yml down
```

### Create hosts data in the Database

First, start the `mq` service by running the following command in a new terminal:

```bash
pipenv shell
# You will probably need to add a new host line in the /etc/hosts file for kafka service
sudo echo "127.0.0.1   kafka" >> /etc/hosts
# Run the MQ service for the Inventory
make run_inv_mq_service
```

Open a new terminal, and run the following commands to create some hosts:

```bash
pipenv shell
make run_inv_mq_service_test_producer NUM_HOSTS=800
```

By default, if you don't pass `NUM_HOSTS` as parameter, it will create only one host in the database.

In the terminal running the `mq` service, you should see all the events passing and the hosts creation logs.

## Creating Export Service Events

To be able to play with the export service, you have to follow the previous steps above:

1. Running the containers (See *Initiate the database* section above)
2. And creating some hosts (See *Create hosts data in the Database* section above)

### Run the export service event loop

In one terminal, run the following command:

```bash
pipenv shell
make run_inv_export_service
```

In one other terminal, generate event towards the export service with the following command:

```bash
make sample-request-create-export
```

By default, it will send a json format request. However, you can choose the format you want, as below:

```bash
make sample-request-create-export format=[json|csv]
```

To modify the data sent to the export service, take a look at the `example_[json|csv]_export_request.json`

## Running the Tests

You can run the tests using pytest:

```bash
pytest --cov=.
```

Or you can run the tests individually:

```bash
./test_api.py
pytest test_db_model.py
./test_unit.py
pytest test_json_validators.py
```

Depending on the environment, it might be necessary to set the DB related environment
variables (`INVENTORY_DB_NAME`, `INVENTORY_DB_HOST`, etc).

## Sonar Integration

This project uses SonarQube to perform static code analysis, monitor test coverage, and find potential issues in the Host Inventory codebase.
The analysis is run automatically for each PR by the ["host-inventory pr security scan" Jenkins job](https://ci.int.devshift.net/job/RedHatInsights-insights-host-inventory-pr-check/).
The results are uploaded to RedHat's SonarQube server, on the [console.redhat.com:insights-host-inventory project](https://sonarqube.corp.redhat.com/dashboard?id=console.redhat.com%3Ainsights-host-inventory).

## Contributing

This repository uses [pre-commit](https://pre-commit.com) to check and enforce code style. It uses
[Black](https://github.com/psf/black) to reformat the Python code and [Flake8](http://flake8.pycqa.org) to check it
afterwards. Other formats and text files are linted as well.

Install pre-commit hooks to your local repository by running:

```bash
pre-commit install
```

After that, all your commited files will be linted. If the checks don’t succeed, the commit will be rejected, but the altered files from the linting will be ready for you to commit again if the issue was automatically correctable.

If you're inside the Red Hat network, please also make sure you have rh-pre-commit installed; instructions on installation can be found [here](https://url.corp.redhat.com/rh-pre-commit#quickstart-install). Then, verify the installation by following the [Testing the Installation](https://url.corp.redhat.com/rh-pre-commit#testing-the-installation) section.
If you follow the instructions for Quickstart Install, and then re-enable running hooks in the repo's `.pre-commit-config.yaml` (instructions in the [Manual Install section](https://url.corp.redhat.com/rh-pre-commit#manual-install)), both hooks should run upon making a commit.

Please make sure all checks pass before submitting a pull request. Thanks!

## Running the server locally

Prometheus was designed to run in a multi-threaded
environment whereas gunicorn uses a multi-process
architecture.  As a result, there is some work
to be done to make prometheus integrate with
gunicorn.

A temp directory for prometheus needs to be created
before the server starts.  The prometheus_multiproc_dir
environment needs to point to this directory.  The
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

Honcho provides a command to run MQ and web services at once:

```bash
honcho start
```

## Identity

It is necessary to provide a valid Identity both when testing the API, and when producing messages via Kafka.
For Kafka messages, the Identity must be set in the `platform_metadata.b64_identity` field of the message.
When testing the API, it must be provided in the authentication header `x-rh-identity` on each call to the service.
For testing purposes, this required identity header can be set to the following:

```curl
x-rh-identity: eyJpZGVudGl0eSI6eyJvcmdfaWQiOiJ0ZXN0IiwidHlwZSI6IlVzZXIiLCJhdXRoX3R5cGUiOiJiYXNpYy1hdXRoIiwidXNlciI6eyJ1c2VybmFtZSI6InR1c2VyQHJlZGhhdC5jb20iLCJlbWFpbCI6InR1c2VyQHJlZGhhdC5jb20iLCJmaXJzdF9uYW1lIjoidGVzdCIsImxhc3RfbmFtZSI6InVzZXIiLCJpc19hY3RpdmUiOnRydWUsImlzX29yZ19hZG1pbiI6ZmFsc2UsImlzX2ludGVybmFsIjp0cnVlLCJsb2NhbGUiOiJlbl9VUyJ9fX0=
```

This is the Base64 encoding of the following JSON document:

```json
{"identity":{"org_id":"test","type":"User","auth_type":"basic-auth","user":{"username":"tuser@redhat.com","email":"tuser@redhat.com","first_name":"test","last_name":"user","is_active":true,"is_org_admin":false,"is_internal":true,"locale":"en_US"}}}
```

The above header has the "User" identity type, but it's possible to use a "System" type header as well.

```curl
x-rh-identity: eyJpZGVudGl0eSI6eyJvcmdfaWQiOiAidGVzdCIsICJhdXRoX3R5cGUiOiAiY2VydC1hdXRoIiwgInN5c3RlbSI6IHsiY2VydF90eXBlIjogInN5c3RlbSIsICJjbiI6ICJwbHhpMTN5MS05OXV0LTNyZGYtYmMxMC04NG9wZjkwNGxmYWQifSwidHlwZSI6ICJTeXN0ZW0ifX0=
```

This is the Base64 encoding of the following JSON document:

```json
{"identity":{"org_id": "test", "auth_type": "cert-auth", "system": {"cert_type": "system", "cn": "plxi13y1-99ut-3rdf-bc10-84opf904lfad"},"type": "System"}}
```

If you want to encode other JSON documents, you can use the following command:

```shell
echo -n '{"identity": {"org_id": "0000001", "type": "System"}}' | base64 -w0
```

### Identity Enforcement

The Identity provided limits access to specific hosts. For API requests, the user can only access
Hosts which have the same Org ID as the provided Identity. For Host updates via Kafka messages,
A Host can only be updated if not only the Org ID matches, but also the `Host.system_profile.owner_id`
matches the provided `identity.system.cn` value.

## Using the legacy api

Some apps still need to use the legacy API path, which by default is `/r/insights/platform/inventory/v1/`.
In case legacy apps require this prefix to be changed, it can be modified using this environment variable:

```bash
 export INVENTORY_LEGACY_API_URL="/r/insights/platform/inventory/api/v1"
```

## Payload Tracker Integration

The inventory service has been integrated with the Payload Tracker service.  The payload
tracker integration can be configured using the following environment variables:

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
PAYLOAD_TRACKER_KAFKA_TOPIC=platform.payload-status
PAYLOAD_TRACKER_SERVICE_NAME=inventory
PAYLOAD_TRACKER_ENABLED=true
```

The payload tracker can be disabled by setting the PAYLOAD_TRACKER_ENABLED environment
variable to _false_. The payload tracker will also be disabled for add/delete operations
that do not include a request_id.  When the payload tracker is disabled, a NullObject
implementation (NullPayloadTracker) of the PayloadTracker interface is used.
The NullPayloadTracker implements the PayloadTracker interface but the methods are _no-op_ methods.

The PayloadTracker purposefully eats all exceptions that it generates. The exceptions are logged.
A failure/exception within the PayloadTracker should not cause a request to fail.

The payload status is a bit "different" due to each "payload" potentially containing
multiple hosts. For example, the add_host operation will only log an error for the
payload if the entire payload fails (catastrophic failure during processing...db down, etc).
One or more of the hosts could fail during the add_host method. These will get logged
as a "processing_error". If a host is successfully added/updated, then it will be logged
as a "processing_success". Having one or more hosts get logged as "processing_error"
will not cause the payload to be flagged as "error" overall.

The payload tracker status logging for the delete operation is similar. The overall status
of the payload will only be logged as an "error" if the entire delete operation fails
(a 404 due to the hosts not existing, db down, etc).

## Generating a database migration script

Run this command to generate a new revision in `migrations/versions`

```bash
make migrate_db message="Description of revision"
```

## Building a docker container image

A [Dockerfile](./dev.dockerfile) is provided for building local Docker containers.
The container image built this way is only intended for development purposes (e.g. orchestrating the container using docker-compose) and must not be used for production deployment.

**Note** some of the packages require a subscription. Make sure the host building the image is attached to a valid subscription providing RHEL.

```bash
docker build . -f dev.dockerfile -t inventory:dev
```

By default, the container runs the database migrations and then starts the inventory-mq service.

## Metrics

The application provides some management information about itself. These
endpoints are exposed at the root path _/_ and thus are accessible only
from inside of the cluster.

* _/health_ responds with _200_ to any GET requests; point your liveness
  or readiness probe here.
* _/metrics_ offers metrics and monitoring intended to be pulled by
  [Prometheus](https://prometheus.io).
* _/version_ responds with a json doc that contains the build version info
  (the value of the OPENSHIFT_BUILD_COMMIT environment variable)

Cron jobs such as `reaper` and `sp-validator` push their metrics to a
[Prometheus Pushgateway](https://github.com/prometheus/pushgateway/) instance
running at _PROMETHEUS_PUSHGATEWAY_. Defaults to _localhost:9091_.

## Release process

This section describes the process of getting a code change from a pull request all the way to production.

### 1. Pull request

It all starts with a [pull request](https://github.com/RedHatInsights/insights-host-inventory/pulls).
When a new pull request is opened, some jobs are run automatically.
These jobs are defined in app-interface [here](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/build.yml).

* [host-inventory pr-checker](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-pr-check) runs the following:
  * [database migrations](#initialize-the-database)
  * [code style checks](#contributing)
  * unit tests
* `ci.ext.devshift.net PR build - All tests` runs _all_ of the IQE tests on the PR's code.
* [host-inventory build-master](https://ci.ext.devshift.net/job/RedHatInsights-insights-host-inventory-gh-build-master/) builds the container image, and pushes it to Quay, where it is scanned for vulnerabilities.

Should any of these fail this is indicated directly on the pull request.

When all of these checks pass and a reviewer approves the changes the pull request can be merged by someone from the [@RedHatInsights/host-based-inventory-committers](https://github.com/orgs/RedHatInsights/teams/host-based-inventory-committers) team.

### 2. Latest image and smoke tests

When a pull request is merged to master, a new container image is built and tagged as [insights-inventory:latest](https://quay.io/repository/cloudservices/insights-inventory?tab=tags).
This image is then automatically deployed to the [Stage environment](https://console-openshift-console.apps.crcs02ue1.urby.p1.openshiftapps.com/k8s/cluster/projects/host-inventory-stage).

### 3. QE testing in the Stage environment

Once the image lands in the Stage environment, the QE testing can begin.
People in [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) run the full IQE test suite against Stage, and then report the results in the [#platform-inventory-standup channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T).

### 4. Promoting the image to the production environment

In order to promote a new image to the production environment, it is necessary to update the [deploy-clowder.yml](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy-clowder.yml) file.
The `ref` parameter on the `prod-host-inventory-prod` namespace needs to be updated to the SHA of the validated image.

Once the change has been made, submit a merge request to [app-interface](https://gitlab.cee.redhat.com/service/app-interface).
For the CI pipeline to run tests on your fork, you'll need to add [@devtools-bot](https://gitlab.cee.redhat.com/devtools-bot) as a Maintainer.
See this [guide](https://docs.gitlab.com/ee/user/project/members/share_project_with_groups.html#sharing-a-project-with-a-group-of-users) on how to do that.

After the MR has been opened, somebody from [AppSRE/insights-host-inventory](https://github.com/orgs/app-sre/teams/insights-host-inventory) will review and approve the MR by adding a `/lgtm` comment.
Afterwards, the MR will be merged automatically and the changes will be deployed to the production environment.
The engineer who approved the MR is then **responsible for monitoring of the rollout of the new image**.

Once that happens, contact [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) and request the image to be re-tested in the production environment.
The new image will also be tested automatically when the [Full Prod Check pipeline](https://main-jenkins-csb-insights-qe.apps.ocp-c1.prod.psi.redhat.com/job/inventory/job/prod-basic/) is run (twice daily).

### Monitoring of deployment

It is essential to monitor the health of the service during and after the production deployment.
A non-exhaustive list of things to watch includes:

* Deployments in the [host-inventory-prod OSD namespace](https://console-openshift-console.apps.crcp01ue1.o9m8.p1.openshiftapps.com/k8s/cluster/projects/host-inventory-prod)
  * primarily ensure that the new pods are spun up properly
* [#team-consoledot-inventory Slack channel](https://app.slack.com/client/T027F3GAJ/C01A49ZGQ05) for any inventory-related Prometheus alerts
* [Inventory Dashboard](https://grafana.app-sre.devshift.net/d/EiIhtC0Wa/inventory?orgId=1&refresh=5m) for any anomalies such as error rate or consumer lag
* [Kibana](https://kibana.apps.crcp01ue1.o9m8.p1.openshiftapps.com/app/kibana#/discover?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-24h,to:now))&_a=(columns:!(_source),filters:!(),index:'43c5fed0-d5ce-11ea-b58c-a7c95afd7a5d',interval:auto,query:(language:lucene,query:'@log_group:%20%22host-inventory-prod%22%20AND%20levelname:%20ERROR'),sort:!(!('@timestamp',desc)))) for any error-level log entries

### Deployment rollback

Should unexpected problems occur during the deployment, it is possible to do a rollback.
This is done by updating the `ref` parameter in deploy-clowder.yml to point to the previous commit SHA, or by reverting the MR that triggered the production deployment.

## Updating the System Profile

In order to add or update a field on the System Profile, first follow the instructions in the [inventory-schemas repo](https://github.com/RedHatInsights/inventory-schemas#contributing).
After an inventory-schemas PR has been accepted and merged, HBI must be updated to keep its own schema in sync.
To do this, simply run this command:

```bash
make update-schema
```

This will pull the latest version of the System Profile schema from inventory-schemas and update files as necessary.
Open a PR with these changes, and it will be reviewed and merged as per [the standard process](#release-process).

## Running ad hoc jobs using a different image

There may be a job (ClowdJobInvocation) which requires using a special image that is different from the one used by the parent application, i.e. host-inventory.  Clowder out-of-the-box does not allow it.  [Running a Special Job](docs/running_special_job.md) describes how to accomplish it.
