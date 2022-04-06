# Host Based Inventory

You've arrived at the repo for the backend of the Host Based Inventory (HBI).
If you're looking for API, integration or user documentation for HBI please see the [Inventory section in our Platform Docs site](https://consoledot.pages.redhat.com/docs/dev/services/inventory.html).

## Getting Started

### Snappy

This project uses [Snappy compression](http://google.github.io/snappy/) to enhance its Kafka usage.
The `python-snappy` package requires the core Snappy library to be installed on the machine, so start off by running the following:

```
sudo dnf install snappy
```

### Install dependencies

This project uses pipenv to manage the development and deployment environments.
To set the project up for development, we recommend using [pyenv](https://github.com/pyenv/pyenv) to install/manage the appropriate python (currently 3.8.x), pip and pipenv version. Once you have pipenv, do the following:

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

### Initialize the database

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
gunicorn -c gunicorn.conf.py run
```

Running the server locally for development. In this case it’s not necessary to
care about the Prometheus temp directory or to set the
_prometheus_multiproc_dir_ environment variable. This is done automatically.

```
python run_gunicorn.py
```

# Running all services locally

Honcho provides a command to run MQ and web services at once:

```
$ honcho start
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

## Identity

It is necessary to provide a valid Identity both when testing the API, and when producing messages via Kafka.
For Kafka messages, the Identity must be set in the `platform_metadata.b64_identity` field of the message.
When testing the API, it must be provided in the authentication header `x-rh-identity` on each call to the service.
For testing purposes, this required identity header can be set to the following:

```
x-rh-identity: eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6InRlc3QiLCJ0eXBlIjoiVXNlciIsImF1dGhfdHlwZSI6ImJhc2ljLWF1dGgiLCJ1c2VyIjp7InVzZXJuYW1lIjoidHVzZXJAcmVkaGF0LmNvbSIsImVtYWlsIjoidHVzZXJAcmVkaGF0LmNvbSIsImZpcnN0X25hbWUiOiJ0ZXN0IiwibGFzdF9uYW1lIjoidXNlciIsImlzX2FjdGl2ZSI6dHJ1ZSwiaXNfb3JnX2FkbWluIjpmYWxzZSwiaXNfaW50ZXJuYWwiOnRydWUsImxvY2FsZSI6ImVuX1VTIn19fQo=
```

This is the Base64 encoding of the following JSON document:

```json
{"identity":{"account_number":"test","type":"User","auth_type":"basic-auth","user":{"username":"tuser@redhat.com","email":"tuser@redhat.com","first_name":"test","last_name":"user","is_active":true,"is_org_admin":false,"is_internal":true,"locale":"en_US"}}}
```

The above header has the "User" identity type, but it's possible to use a "System" type header as well.

```
x-rh-identity: eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6ICJ0ZXN0IiwgImF1dGhfdHlwZSI6ICJjZXJ0LWF1dGgiLCAiaW50ZXJuYWwiOiB7Im9yZ19pZCI6ICIzMzQwODUxIn0sICJzeXN0ZW0iOiB7ImNlcnRfdHlwZSI6ICJzeXN0ZW0iLCAiY24iOiAicGx4aTEzeTEtOTl1dC0zcmRmLWJjMTAtODRvcGY5MDRsZmFkIn0sInR5cGUiOiAiU3lzdGVtIn19
```

This is the Base64 encoding of the following JSON document:

```json
{"identity":{"account_number": "test", "auth_type": "cert-auth", "internal": {"org_id": "3340851"}, "system": {"cert_type": "system", "cn": "plxi13y1-99ut-3rdf-bc10-84opf904lfad"},"type": "System"}}
```

If you want to encode other JSON documents, you can use the following command:

```shell
echo '{"identity": {"account_number": "0000001", "type": "System", "internal": {"org_id": "000001"}}}' | base64
```

### Identity Enforcement

The Identity provided limits access to specific hosts. For API requests, the user can only access
Hosts which have the same Account as the provided Identity. For Host updates via Kafka messages,
A Host can only be updated if not only the Account matches, but also the `Host.system_profile.owner_id`
matches the provided `identity.system.cn` value.

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

## Integrating with Cross Join (xjoin)

1. Clone [xjoin-kstreams](https://github.com/RedHatInsights/xjoin-kstreams/)
2. Follow the instructions for local development in the [xjoin-kstreams README](https://github.com/RedHatInsights/xjoin-kstreams/#xjoin-kstreams). Stop after you run `dev/start.sh`. This will create a docker-compose environment with the following.
    | Service | Port on localhost |
    | ------- | ----------------- |
    | Inventory DB | 5432 |
    | Advisor DB | 5433 |
    | Vulnerability DB | 5434 |
    | Zookeeper | 2181 |
    | Kafka | 29092 |
    | Kafka Connect | 8083 |
    | Kafka Schema Registry | 8081 |
    | xjoin-search | 4000 |
    | ElasticSearch | 9200, 9300 |

3. `cd` into the root of this project (host inventory)
4. Run the inventory-mq-service
```
make run_inv_mq_service
```

5. Run the inventory api
```
make run_inv_web_service
```

6. Produce a kafka message
```
make run_inv_mq_service_test_producer
```

7. Validate the host is in xjoin
```
curl \
-H 'Content-Type: application/json' \
-H 'x-rh-identity: eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6InRlc3QiLCJ0eXBlIjoiVXNlciIsInVzZXIiOnsidXNlcm5hbWUiOiJ0dXNlckByZWRoYXQuY29tIiwiZW1haWwiOiJ0dXNlckByZWRoYXQuY29tIiwiZmlyc3RfbmFtZSI6InRlc3QiLCJsYXN0X25hbWUiOiJ1c2VyIiwiaXNfYWN0aXZlIjp0cnVlLCJpc19vcmdfYWRtaW4iOmZhbHNlLCJpc19pbnRlcm5hbCI6dHJ1ZSwibG9jYWxlIjoiZW5fVVMifX19' \
--data-binary '{"query":"{hosts(limit:10,offset:0){meta{count,total}data{id account display_name}}}"}' \
http://localhost:4000/graphql
```

8. Now you can curl against the inventory-api with xjoin enabled
```
curl \
-H 'x-rh-identity: eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6InRlc3QiLCJ0eXBlIjoiVXNlciIsInVzZXIiOnsidXNlcm5hbWUiOiJ0dXNlckByZWRoYXQuY29tIiwiZW1haWwiOiJ0dXNlckByZWRoYXQuY29tIiwiZmlyc3RfbmFtZSI6InRlc3QiLCJsYXN0X25hbWUiOiJ1c2VyIiwiaXNfYWN0aXZlIjp0cnVlLCJpc19vcmdfYWRtaW4iOmZhbHNlLCJpc19pbnRlcm5hbCI6dHJ1ZSwibG9jYWxlIjoiZW5fVVMifX19' \
-H 'x-rh-cloud-bulk-query-source: xjoin' \
localhost:8080/api/inventory/v1/hosts
```

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

When all of these checks pass and a reviewer approves the changes the pull request can be merged by someone from the [@RedHatInsights/host-based-inventory-committers ](https://github.com/orgs/RedHatInsights/teams/host-based-inventory-committers) team.

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

## 4. QE testing in the QA environment

Once the stable image lands in the QA environment, the QE testing can begin.

People in [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) Slack group handle this part.
They trigger the QE testing jobs \[[1](https://jenkins-jenkins.5a9f.insights-dev.openshiftapps.com/view/QE/job/qe/job/iqe-inventory-plugin-kafka-qa/)\]\[[2](https://insights-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/view/Inventory/job/iqe-host-inventory-qa-basic/)\]. Optionally, manual testing may be performed to validate certain features / bug fixes.

Once all of this is finished, a [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) representative (manually) reports the results in the [#platform-inventory-standup channel](https://app.slack.com/client/T026NJJ6Z/CQFKM031T).

## 5. Promoting the image to stage environment

This step can be performed in parallel with step 4.

In order to promote a new image to the stage environment it is necessary to update the [deploy.yml](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/host-inventory/deploy.yml) file.
The `IMAGE_TAG` parameter needs to be updated to the current _PROMO_CODE_ (truncated to first 7 characters).
This applies to the following components:

* insights-inventory-reaper
* insights-inventory-mq-service
* insights-inventory

The `IMAGE_TAG` parameter should be updated for the stage namespace for each of the aforementioned components.
Note that `insights-host-delete`, which uses a different image, should not be updated.

There is a script _utils/deploy.py_ that can be used to automatically update the `IMAGE_TAG`. Possible usage using
_sponge_ from [_moreutils_](http://joeyh.name/code/moreutils/):

```bash
$ pipenv run python utils/deploy.py -s PROMO_CODE < ../app-interface/data/services/insights/host-inventory/deploy.yml | sponge ../app-interface/data/services/insights/host-inventory/deploy.yml
```

Once the change has been made, submit a merge request to [app-interface](https://gitlab.cee.redhat.com/service/app-interface).
For the CI pipeline to run tests on your fork, add [@devtools-bot](https://gitlab.cee.redhat.com/devtools-bot) as a Maintainer.
See this [guide](https://docs.gitlab.com/ee/user/project/members/share_project_with_groups.html#sharing-a-project-with-a-group-of-users) on how to do that.

After the MR has been opened, get somebody from [AppSRE/insights-host-inventory](https://github.com/orgs/app-sre/teams/insights-host-inventory) to approve the MR by adding a `/lgtm` comment.
Afterwards, the MR is merged automatically and changes are deployed to the stage environment.

Once that happens, contact [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) and request the image to be tested in the stage environment.

## 6. Promoting the image to production

Once [@platform-inventory-qe](https://app.slack.com/client/T026NJJ6Z/browse-user-groups/user_groups/S011SJB6S5R) finishes testing of the image in both qa and stage environments (i.e. steps 4 and 5 are completed) they propose a release to production.

They do so by opening a MR in [app-interface](https://gitlab.cee.redhat.com/service/app-interface) to update the `IMAGE_TAG` in the production namespace to the _PROMO_CODE_.
The same steps to create a MR to app-interface are followed as defined in step 5 except that the `IMAGE_TAG` parameter for the prod (instead of stage) namespace is changed.

```bash
$ pipenv run python utils/deploy.py -p PROMO_CODE < ../app-interface/data/services/insights/host-inventory/deploy.yml | sponge ../app-interface/data/services/insights/host-inventory/deploy.yml
```

### Service owner approval

Once the MR has been created, an engineer, who is a member of [AppSRE/insights-host-inventory](https://github.com/orgs/app-sre/teams/insights-host-inventory) and has been trained to perform inventory releases, approves the MR by adding a `/lgtm` comment.
The engineer is then **responsible for monitoring of the rollout of the new image**.

### Monitoring of deployment

It is essential to monitor the health of the service during and after the production deployment.
A non-exhaustive list of things to watch includes:

* Inventory deployments in [platform-prod OSD namespace](https://console-openshift-console.apps.crcp01ue1.o9m8.p1.openshiftapps.com/topology/ns/platform-prod/list)
  * primarily ensure that the new pods are spun up properly
* [#team-insights-alerts Slack channel](https://app.slack.com/client/T027F3GAJ/C015X9ZF621/details) for any inventory-related Prometheus alerts
* [Inventory Dashboard](https://grafana.app-sre.devshift.net/d/EiIhtC0Wa/inventory?orgId=1&var-datasource=crcp01ue1-prometheus) for any anomalies such as error rate or consumer lag
* [Kibana](https://kibana.apps.crcp01ue1.o9m8.p1.openshiftapps.com/app/kibana#/discover?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-15m,to:now))&_a=(columns:!(_source),filters:!(),index:'43c5fed0-d5ce-11ea-b58c-a7c95afd7a5d',interval:auto,query:(language:lucene,query:'(@log_stream:%20%22inventory-reaper%22%20OR%20@log_stream:%20%22inventory-mq%22%20OR%20@log_stream:%20%22insights-inventory%22)%20AND%20levelname:%20ERROR'),sort:!(!('@timestamp',desc)))) for any error-level log entries

### Deployment rollback

Should unexpected problems occur during the deployment, it is possible to do a rollback.
This is done by updating the `IMAGE_TAG` parameters in deploy.yml to point to a previous _PROMO_CODE_.
