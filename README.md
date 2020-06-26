# Host Based Inventory

You've arrived at the repo for the backend of the Host Based Inventory (HBI).If you're
looking for API, integration or user documentation for HBI please see the [Inventory section
in our Platform Docs site] (https://platform-docs.cloud.paas.psi.redhat.com/backend/inventory.html).

# Getting Started

This project uses pipenv to manage the development and deployment environments.
To set the project up for development, we recommend using [pyenv](https://github.com/pyenv/pyenv) to install/manage the appropriate python (currently 3.6.x), pip and pipenv version. Once you have pipenv, do the following:

```
pipenv install --dev
```

Afterwards you can activate the virtual environment by running:

```
pipenv shell
```

Included is a docker-compose file `dev.yml` that will start a postgres database that is
useful for development.

```
docker-compose -f dev.yml up
```

## Initialize the database

Run the following commands to run the db migration scripts which will
maintain the db tables.

The database migration scripts determine the DB location, username,
password and db name from the INVENTORY_DB_HOST, INVENTORY_DB_USER,
INVENTORY_DB_PASS and INVENTORY_DB_NAME environment variables.

```
python manage.py db upgrade
```

By default the database container will use a bit of local storage so that data
you enter will be persisted across multiple starts of the container.  If you
want to destroy that data do the following:

```
docker-compose down
```

## Running the Tests

It is possible to run the tests using pytest:

```
pytest --cov=.
```

Or you can run the tests individually:

```
./test_api.py
pytest test_db_model.py
./test_unit.py
pytest test_json_validators.py
```

Depending on the environment, it might be necessary to set the DB related environment
variables (INVENTORY_DB_NAME, INVENTORY_DB_HOST, etc).

## Contributing

This repository uses [pre-commit](https://pre-commit.com) to check and enforce code style. It uses
[Black](https://github.com/psf/black) to reformat the Python code and [Flake8](http://flake8.pycqa.org) to check it
afterwards. Other formats and text files are linted as well.

Install pre-commit hooks to your local repository by running:

```bash
$ pre-commit install
```

After that, all your commited files will be linted. If the checks don’t succeed, the commit will be rejected. Please
make sure all checks pass before submitting a pull request. Thanks!

# Running the server locally

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

A command to run the server in a cluster.

```
gunicorn -c gunicorn.conf.py --log-config=$INVENTORY_LOGGING_CONFIG_FILE run
```

Running the server locally for development. In this case it’s not necessary to
care about the Prometheus temp directory or to set the
_prometheus_multiproc_dir_ environment variable. This is done automatically.

```
python run_gunicorn.py
```

## Config env vars

```
 prometheus_multiproc_dir=/path/to/prometheus_dir
 APP_NAME="inventory"
 PATH_PREFIX="/r/insights/platform"
 INVENTORY_DB_USER="insights"
 INVENTORY_DB_PASS="insights"
 INVENTORY_DB_HOST="localhost"
 INVENTORY_DB_NAME="insights"
 INVENTORY_DB_POOL_TIMEOUT="5"
 INVENTORY_DB_POOL_SIZE="5"
 INVENTORY_LOGGING_CONFIG_FILE=logconf.ini
 INVENTORY_DB_SSL_MODE=""
 INVENTORY_DB_SSL_CERT=""
```

To force an ssl connection to the db set INVENTORY_DB_SSL_MODE to "verify-full"
and provide the path to the certificate you'd like to use.

## Testing API Calls

It is necessary to pass an authentication header along on each call to the
service.  For testing purposes, it is possible to set the required identity
header to the following:

```
x-rh-identity: eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMDAwMDAwMSIsICJpbnRlcm5hbCI6IHsib3JnX2lkIjogIjAwMDAwMSJ9fX0=
```

This is the Base64 encoding of the following JSON document:

```json
{"identity": {"account_number": "0000001", "internal": {"org_id": "000001"}}}
```

## Using the legacy api

In case one needs to do this:

```
 export INVENTORY_LEGACY_API_URL="/r/insights/platform/inventory/api/v1"
```

## Payload Tracker Integration

The inventory service has been integrated with the Payload Tracker service.  The payload
tracker integration can be configured using the following environment variables:

```
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


# Generating a migration script

Run this command to generate a new revision in `migrations/versions`

```
python manage.py db revision -m "Description of revision"
```

# Building a container image

Inventory uses [Source-To-Image (S2I)](https://github.com/openshift/source-to-image) for building of container images.
The container image is built by running

```
s2i build . centos/python-36-centos7 inventory -e ENABLE_PIPENV=true
```

## Building with docker

In addition, a [Dockerfile](./dev.dockerfile) is provided.
The container image built this way is only intended for development purposes (e.g. orchestrating the container using docker-compose) and must not be used for production deployment.

```
docker build . -f dev.dockerfile -t inventory:dev
```

By default, the container runs the database migrations and then starts the inventory-mq service.

# Deployment

The application provides some management information about itself. These
endpoints are exposed at the root path _/_ and thus are accessible only
from inside of the deployment cluster.

* _/health_ responds with _200_ to any GET requests, point your liveness
  or readiness probe here.
* _/metrics_ offers metrics and monitoring intended to be pulled by
  [Prometheus](https://prometheus.io).
* _/version_ responds with a json doc that contains the build version info
  (the value of the OPENSHIFT_BUILD_COMMIT environment variable)

Cron jobs push their metrics to a
[Prometheus Pushgateway](https://github.com/prometheus/pushgateway/) instance
running at _PROMETHEUS_PUSHGATEWAY_. Defaults to _localhost:9091_.

# Release process

This section describes the process of getting a code change from a pull request all the way to production.

## 1. Pull request

It all starts with a [pull request](https://github.com/RedHatInsights/insights-host-inventory/pulls).
When a new pull request is opened the following checks are [run automatically](https://github.com/RedHatInsights/insights-host-inventory/blob/master/Jenkinsfile):

* [database migrations](#initialize-the-database)
* [code style checks](#contributing)
* unit tests

Should any of these fail this is indicated directly on the pull request.

When all of these checks pass and a reviewer approves the changes the pull request can be merged.
Currently [@Glutexo](https://github.com/Glutexo) and [@jharting](https://github.com/jharting) are authorized to merge pull requests.

## 2. Latest image and smoke tests

When a pull request is merged to master a new container image is built and tagged as [insights-inventory:latest](https://console.insights-dev.openshift.com/console/project/buildfactory/browse/images/insights-inventory/latest?tab=body).
The latest image is deployed to the [CI environment](https://console.insights-dev.openshift.com/console/project/platform-ci/overview) automatically. This is announced in [#platform-inventory-standup slack channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T) as _Inventory release pipeline (step 1)_

Afterwards, the smoke tests are started automatically. These consist of a subset of [IQE tests](https://gitlab.cee.redhat.com/insights-qe) that cover inventory, advisor, engine and the ingress service.

Once the smoke test run finishes the results are reported in [#platform-inventory-standup slack channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T) as _Inventory release pipeline (step 2)_

If the smoke tests pass, the container image is re-tagged as [insights-inventory:stable](https://console.insights-dev.openshift.com/console/project/buildfactory/browse/images/insights-inventory/stable?tab=body)

### Suppressing automatic propagation to stable

In certain situations it may be desired for an image to stay deployed in CI only for some time before proceeding with the QA deployment.
An example would be a possibly breaking change where we want to give integrators some time to test the integration in CI first.
This can be achieved by setting the `promote-stable` key to `false` in the [inventory-pipeline config map](https://console.insights-dev.openshift.com/console/project/buildfactory/browse/config-maps/inventory-pipeline).
This change needs to be made **before the given commit is merged to master**.

## 3. Vortex

[Vortex](https://github.com/RedHatInsights/e2e-deploy/blob/master/docs/pipeline.md#overview) is a process that picks stable images of platform components and tests them together. The process is automated and runs periodically.
By default the [vortex job](https://jenkins-insights-qe-ci.cloud.paas.psi.redhat.com/blue/organizations/jenkins/vortex-test-suite/activity) runs around every two hours.

Once the vortex tests are finished the stable inventory image is tagged as [insights-inventory:qa](https://console.insights-dev.openshift.com/console/project/buildfactory/browse/images/insights-inventory/qa?tab=body) and deployed to the [QA environment](https://console.insights-dev.openshift.com/console/project/platform-qa/overview).
This is announced in [#platform-inventory-standup slack channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T) as _Inventory release pipeline (step 3)_.

## 4. QE testing

Once the stable image lands in the QA environment, the QE testing can begin.

People in [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) Slack group handle this part.
They trigger the QE testing jobs \[[1](https://jenkins-jenkins.5a9f.insights-dev.openshiftapps.com/view/QE/job/qe/job/iqe-inventory-plugin-kafka-qa/)\]\[[2](https://insights-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/view/Inventory/job/iqe-host-inventory-qa-basic/)\]. Optionally, manual testing may be performed to validate certain features / bug fixes.

Once all of this is finished, a [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) representative (manually) reports the results in the [#platform-inventory-standup channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T).

## 5. Promoting the image to production

Once the image has passed QE testing, it can be promoted to production.

### Triggering the production deployment

This is done using a [Jenkins job](https://jenkins-insights-jenkins.1b13.insights.openshiftapps.com/job/platform-prod/job/platform-prod-insights-inventory-deployer/build).
The SHA of the HEAD commit should be used as _PROMO_CODE_.

A new deployment is announced in [#platform-inventory-standup slack channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T) as _Inventory release pipeline (step 4)_

### Monitoring of the production deployment

It is essential to monitor the health of the service during and after the production deployment.
A non-exhaustive list of things to watch includes:

* Inventory deployments in [platform-prod OSD namespace](https://console.insights.openshift.com/console/project/platform-prod/overview)
  * primarily ensure that the new pods are spun up properly
* [#platform-inventory-standup Slack channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T) for any Prometheus alerts
* [Inventory Dashboard](https://metrics.1b13.insights.openshiftapps.com/d/EiIhtC0Wa/inventory?orgId=1&var-namespace=prod) for any anomalies such as error rate or consumer lag

### Production rollback

Should unexpected problems occur after a production deployment, it is possible to do a rollback.
The process is the same as above, i.e. the same [Jenkins job](https://jenkins-insights-jenkins.1b13.insights.openshiftapps.com/job/platform-prod/job/platform-prod-insights-inventory-deployer/build).
What differs is that a SHA of a previous commit, to which the deployment should be rolled back, should be used as _PROMO_CODE_.
