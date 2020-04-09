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

a
