# Insights Inventory

This project is the home of the host-based inventory for the Insights Platform.

## Getting Started

This project uses pipenv to manage the development and deployment environments.
To set the project up for development do the following:

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

#### Initialize/update the database tables

Run the following commands to run the db migration scripts which will
maintain the db tables.

The database migration scripts determine the DB location, username,
password and db name from the INVENTORY_DB_HOST, INVENTORY_DB_USER,
INVENTORY_DB_PASS and INVENTORY_DB_NAME environment variables.
```
python manage.py db migrate
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
prometheus_multiproc_dir=/path/to/prometheus_multiprocess/ pytest --cov=.
```

Or you can run the tests individually:

```
prometheus_multiproc_dir=/path/to/prometheus_multiprocess/ ./test_api.py
prometheus_multiproc_dir=/path/to/prometheus_multiprocess/ pytest test_db_model.py
./test_unit.py
pytest test_json_validators.py
```

Depending on the environment, it might be necessary to set the DB related environment
variables (INVENTORY_DB_NAME, INVENTORY_DB_HOST, etc).  See information on
_prometheus_multiproc_dir_ environment variable below.

## Running the server

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


## Configuration environment variables

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
```


## Using the legacy api

```
 export INVENTORY_LEGACY_API_URL="/r/insights/platform/inventory/api/v1"
```


## Deployment

The application provides some management information about itself. These
endpoints are exposed at the root path _/_ and thus are accessible only
from inside of the deployment cluster.

* _/health_ responds with _200_ to any GET requests, point your liveness
  or readiness probe here.
* _/metrics_ offers metrics and monitoring intended to be pulled by
  [Prometheus](https://prometheus.io). 
* _/version_ responds with a json doc that contains the build version info
  (the value of the OPENSHIFT_BUILD_COMMIT environment variable)

## API Documentation

The API is described by an OpenAPI specification file
[_swagger/api/api.spec.yaml_](swagger/api.spec.yaml). The application exposes
a browsable Swagger UI Console at
[_/r/insights/platform/inventory/api/v1/ui/_](http://localhost:8080/r/insights/platform/inventory/api/v1/ui/).

## Operation

The Insights Inventory service is responsible for storing information
about hosts and deduplicating hosts as they are reported.  The
Inventory service uses the canonical facts to perform the deduplication.
The canonical facts are:
* insights_id
* rhel_machine_id
* subscription_manager_id
* satellite_id
* bios_uuid
* ip_addresses
* fqdn
* mac_addresses
* external_id

Hosts are added and updated by sending a POST to the /hosts endpoint.
(See the API Documentation for more details on the POST method).
This method returns an *id* which should be used to reference the host
by other services in the Insights platform.

#### Overview of the deduplication process

If the update request includes an insights_id, then the inventory service
will lookup the host using the insights_id.  If the inventory service
finds a host with a matching insights_id, then the host will be updated
and the canonical facts from the update request will replace the existing
canonical facts.

If the update request does not include an insights_id, then the canonical facts
will be used to lookup the host.  If the canonical facts from the update
request are a subset or a superset of the previously stored canonical facts,
then the host will be updated and any new canonical facts from the request
will be added to the existing host entry.

If the canonical facts based lookup does not locate an existing host, then
a new host entry is created.

#### Testing API Calls

It is necessary to pass an authentication header along on each call to the
service.  For testing purposes, it is possible to set the required identity
header to the following:

  x-rh-identity: eyJpZGVudGl0eSI6eyJhY2NvdW50X251bWJlciI6IjAwMDAwMDEifX0=

This is the base64 encoding of the following json doc:

  '{"identity":{"account_number":"0000001"}}'
